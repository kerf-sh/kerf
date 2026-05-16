"""
Hermetic tests for kerf_cad_core.aero — applied aerodynamics module.

Coverage:
  flow.isa_atmosphere       — troposphere + tropopause + stratosphere + edge cases
  flow.dynamic_pressure     — basic formula + edge cases
  flow.reynolds_number      — basic formula + error cases
  flow.mach_number          — subsonic, transonic warning
  flow.prandtl_glauert_factor — beta calculation
  flow.thin_airfoil_cl/cm   — Cl = 2π(α−α₀), Cm_c4
  flow.finite_wing_cl       — Prandtl lifting line
  flow.induced_drag_coefficient — CDi = CL²/(πARe)
  flow.total_drag_coefficient   — CD = CD0 + CDi
  flow.ld_ratio             — L/D
  flow.best_glide_cl        — max L/D condition
  flow.level_flight_thrust  — T = W × CD/CL
  flow.level_flight_power   — P = T × V
  flow.stall_speed          — V_stall formula
  flow.climb_rate           — RC = (T−D)V/W
  flow.actuator_disc_thrust — T = 2ρA(V+w)w
  flow.propeller_ideal_efficiency — η = V/(V+w)
  flow.breguet_range        — Breguet propeller range
  flow.breguet_endurance    — Breguet propeller endurance

All tests are pure-Python and hermetic: no OCC, no DB, no network, no fixtures.
Formulae verified against Anderson (Introduction to Flight, 8th ed.) hand-calcs.

References
----------
Anderson, J.D. — Introduction to Flight, 8th ed., McGraw-Hill (2016)
Anderson, J.D. — Fundamentals of Aerodynamics, 6th ed., McGraw-Hill (2017)
ICAO Doc 7488  — Manual of the ICAO Standard Atmosphere, 3rd ed. (1993)

Author: imranparuk
"""
from __future__ import annotations

import math
import warnings

import pytest

from kerf_cad_core.aero.flow import (
    isa_atmosphere,
    dynamic_pressure,
    reynolds_number,
    mach_number,
    prandtl_glauert_factor,
    thin_airfoil_cl,
    thin_airfoil_cm,
    finite_wing_lift_slope,
    finite_wing_cl,
    induced_drag_coefficient,
    total_drag_coefficient,
    ld_ratio,
    best_glide_cl,
    level_flight_thrust,
    level_flight_power,
    stall_speed,
    climb_rate,
    actuator_disc_thrust,
    propeller_ideal_efficiency,
    breguet_range,
    breguet_endurance,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REL = 1e-4   # relative tolerance — 0.01% for engineering formula checks


def _rel_close(actual: float, expected: float, tol: float = REL) -> bool:
    if expected == 0.0:
        return abs(actual) < tol
    return abs(actual - expected) / abs(expected) < tol


# ===========================================================================
# 1. ISA Standard Atmosphere
# ===========================================================================

class TestISAAtmosphere:

    def test_sea_level_temperature(self):
        """ISA sea level: T = 288.15 K."""
        r = isa_atmosphere(0.0)
        assert r["ok"] is True
        assert _rel_close(r["T_K"], 288.15)

    def test_sea_level_pressure(self):
        """ISA sea level: p = 101 325 Pa."""
        r = isa_atmosphere(0.0)
        assert _rel_close(r["p_Pa"], 101325.0)

    def test_sea_level_density(self):
        """ISA sea level: ρ = 1.225 kg/m³."""
        r = isa_atmosphere(0.0)
        assert _rel_close(r["rho_kg_m3"], 1.225)

    def test_sea_level_speed_of_sound(self):
        """ISA sea level: a = √(γ R T) = √(1.4 × 287.05287 × 288.15) ≈ 340.29 m/s."""
        r = isa_atmosphere(0.0)
        a_expected = math.sqrt(1.4 * 287.05287 * 288.15)
        assert _rel_close(r["a_m_s"], a_expected)

    def test_tropopause_temperature(self):
        """ISA at 11 000 m: T = 288.15 + (−0.0065)(11000) = 216.65 K."""
        r = isa_atmosphere(11_000.0)
        assert r["ok"] is True
        assert _rel_close(r["T_K"], 216.65)

    def test_tropopause_pressure(self):
        """ISA at 11 000 m: p ≈ 22 632 Pa (ICAO table value)."""
        r = isa_atmosphere(11_000.0)
        # ICAO Doc 7488 gives p = 22 632.1 Pa at 11 km
        assert _rel_close(r["p_Pa"], 22_632.1, tol=1e-3)

    def test_tropopause_density(self):
        """ISA at 11 000 m: ρ ≈ 0.3639 kg/m³ (ICAO table)."""
        r = isa_atmosphere(11_000.0)
        # ICAO: ρ = 0.36392 kg/m³
        assert _rel_close(r["rho_kg_m3"], 0.36392, tol=1e-3)

    def test_stratosphere_isothermal(self):
        """Above 11 km temperature is constant at 216.65 K."""
        r = isa_atmosphere(15_000.0)
        assert r["ok"] is True
        assert _rel_close(r["T_K"], 216.65)

    def test_stratosphere_pressure_decreasing(self):
        """Pressure at 15 km must be less than at 11 km."""
        r11 = isa_atmosphere(11_000.0)
        r15 = isa_atmosphere(15_000.0)
        assert r15["p_Pa"] < r11["p_Pa"]

    def test_density_decreases_with_altitude(self):
        """Density must decrease monotonically."""
        rho_vals = [isa_atmosphere(h)["rho_kg_m3"] for h in (0, 5000, 10000, 15000, 20000)]
        for i in range(len(rho_vals) - 1):
            assert rho_vals[i] > rho_vals[i + 1]

    def test_negative_altitude_returns_error(self):
        """Negative altitude should return ok=False."""
        r = isa_atmosphere(-100.0)
        assert r["ok"] is False

    def test_above_20km_returns_error(self):
        """Altitude > 20 000 m not modelled; should return ok=False."""
        r = isa_atmosphere(25_000.0)
        assert r["ok"] is False

    def test_ideal_gas_consistency(self):
        """Verify ρ = p / (R T) at 8000 m."""
        r = isa_atmosphere(8_000.0)
        rho_check = r["p_Pa"] / (287.05287 * r["T_K"])
        assert _rel_close(r["rho_kg_m3"], rho_check)


# ===========================================================================
# 2. Dynamic pressure
# ===========================================================================

class TestDynamicPressure:

    def test_standard_sea_level(self):
        """q = ½ × 1.225 × 100² = 6125 Pa."""
        r = dynamic_pressure(rho=1.225, V=100.0)
        assert r["ok"] is True
        assert _rel_close(r["q_Pa"], 6125.0)

    def test_zero_velocity(self):
        """V=0 → q=0."""
        r = dynamic_pressure(rho=1.225, V=0.0)
        assert r["ok"] is True
        assert r["q_Pa"] == 0.0

    def test_negative_density_error(self):
        """rho < 0 should return ok=False."""
        r = dynamic_pressure(rho=-1.0, V=50.0)
        assert r["ok"] is False


# ===========================================================================
# 3. Reynolds number
# ===========================================================================

class TestReynoldsNumber:

    def test_known_value(self):
        """Re = ρ V L / μ = 1.225 × 50 × 1.0 / 1.789e-5 ≈ 3.42e6."""
        r = reynolds_number(rho=1.225, V=50.0, L=1.0, mu=1.789e-5)
        assert r["ok"] is True
        expected = 1.225 * 50.0 * 1.0 / 1.789e-5
        assert _rel_close(r["Re"], expected)

    def test_zero_viscosity_error(self):
        """μ = 0 should return ok=False."""
        r = reynolds_number(rho=1.225, V=50.0, L=1.0, mu=0.0)
        assert r["ok"] is False


# ===========================================================================
# 4. Mach number
# ===========================================================================

class TestMachNumber:

    def test_subsonic(self):
        """V=100 m/s, a=340 m/s → M=0.294."""
        r = mach_number(V=100.0, a=340.0)
        assert r["ok"] is True
        assert _rel_close(r["M"], 100.0 / 340.0)
        assert r["transonic"] is False

    def test_transonic_warning(self):
        """V=260 m/s, a=340 m/s → M≈0.76 → transonic warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            r = mach_number(V=260.0, a=340.0)
        assert r["ok"] is True
        assert r["transonic"] is True
        assert any("transonic" in str(x.message).lower() for x in w)

    def test_zero_velocity(self):
        """V=0 → M=0, no warning."""
        r = mach_number(V=0.0, a=340.0)
        assert r["ok"] is True
        assert r["M"] == 0.0


# ===========================================================================
# 5. Prandtl-Glauert factor
# ===========================================================================

class TestPrandtlGlauert:

    def test_incompressible_limit(self):
        """M=0 → β=1."""
        r = prandtl_glauert_factor(0.0)
        assert r["ok"] is True
        assert _rel_close(r["beta"], 1.0)

    def test_m_half(self):
        """M=0.5 → β=√(1-0.25)=√0.75."""
        r = prandtl_glauert_factor(0.5)
        assert r["ok"] is True
        assert _rel_close(r["beta"], math.sqrt(0.75))

    def test_supersonic_rejected(self):
        """M >= 1 should return ok=False."""
        r = prandtl_glauert_factor(1.0)
        assert r["ok"] is False

    def test_transonic_flag(self):
        """M=0.75 → transonic_warning=True."""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            r = prandtl_glauert_factor(0.75)
        assert r["transonic_warning"] is True


# ===========================================================================
# 6. Thin-airfoil theory
# ===========================================================================

class TestThinAirfoil:

    def test_cl_symmetric_zero_aoa(self):
        """α=0, α₀=0 → Cl=0."""
        r = thin_airfoil_cl(0.0, 0.0)
        assert r["ok"] is True
        assert r["Cl"] == 0.0

    def test_cl_formula(self):
        """Cl = 2π × 5° = 2π × 0.08727 ≈ 0.5484."""
        alpha = math.radians(5.0)
        r = thin_airfoil_cl(alpha, 0.0)
        assert r["ok"] is True
        expected = 2.0 * math.pi * alpha
        assert _rel_close(r["Cl"], expected)

    def test_cl_with_alpha0(self):
        """Cl = 2π (α − α₀) for α=3°, α₀=−2°."""
        alpha = math.radians(3.0)
        alpha0 = math.radians(-2.0)
        r = thin_airfoil_cl(alpha, alpha0)
        assert r["ok"] is True
        assert _rel_close(r["Cl"], 2.0 * math.pi * (alpha - alpha0))

    def test_cm_symmetric_airfoil(self):
        """Symmetric airfoil (α₀=0) at α=5°: Cm_c4 = −(π/2)(α)."""
        alpha = math.radians(5.0)
        r = thin_airfoil_cm(alpha, 0.0)
        assert r["ok"] is True
        expected = -(math.pi / 2.0) * alpha
        assert _rel_close(r["Cm_c4"], expected)

    def test_stall_warning_high_aoa(self):
        """Very high AoA should trigger stall_warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            r = thin_airfoil_cl(math.radians(30.0), 0.0)
        assert r["stall_warning"] is True
        assert any("stall" in str(x.message).lower() for x in w)


# ===========================================================================
# 7. Finite-wing (Prandtl lifting line)
# ===========================================================================

class TestFiniteWing:

    def test_lift_slope_elliptical(self):
        """
        For AR=8, e=1 (elliptical), a₀=2π:
          a = 2π / (1 + 2π/(π×8×1)) = 2π / (1 + 0.25) = 2π/1.25 ≈ 5.026 rad⁻¹.
        Anderson, Introduction to Flight, Example 5.2 style.
        """
        r = finite_wing_lift_slope(a0=2.0 * math.pi, AR=8.0, e_planform=1.0)
        assert r["ok"] is True
        expected = (2.0 * math.pi) / (1.0 + (2.0 * math.pi) / (math.pi * 8.0 * 1.0))
        assert _rel_close(r["a_rad_inv"], expected)

    def test_finite_wing_cl_at_5deg(self):
        """
        AR=8, e=1, α=5°, α₀=0:
          a_wing = 2π/1.25 ≈ 5.026 rad⁻¹
          CL = 5.026 × 0.08727 ≈ 0.4385
        """
        alpha = math.radians(5.0)
        r = finite_wing_cl(alpha_rad=alpha, alpha0_rad=0.0, AR=8.0, e_planform=1.0)
        assert r["ok"] is True
        a_wing = (2.0 * math.pi) / (1.0 + (2.0 * math.pi) / (math.pi * 8.0))
        expected_CL = a_wing * alpha
        assert _rel_close(r["CL"], expected_CL)

    def test_finite_wing_cl_less_than_2d(self):
        """Finite-wing CL must be less than thin-airfoil Cl at same AoA (downwash)."""
        alpha = math.radians(8.0)
        cl_2d = thin_airfoil_cl(alpha)["Cl"]
        cl_3d = finite_wing_cl(alpha_rad=alpha, AR=6.0, e_planform=0.85)["CL"]
        assert cl_3d < cl_2d

    def test_induced_drag_coefficient(self):
        """
        CL=0.5, AR=8, e=1:
          CDi = 0.5² / (π×8×1) = 0.25 / 25.133 ≈ 0.009947
        """
        r = induced_drag_coefficient(CL=0.5, AR=8.0, e=1.0)
        assert r["ok"] is True
        expected = 0.25 / (math.pi * 8.0)
        assert _rel_close(r["CDi"], expected)

    def test_induced_drag_zero_lift(self):
        """CL=0 → CDi=0."""
        r = induced_drag_coefficient(CL=0.0, AR=6.0, e=0.85)
        assert r["ok"] is True
        assert r["CDi"] == 0.0


# ===========================================================================
# 8. Drag buildup
# ===========================================================================

class TestDragBuildup:

    def test_total_cd_formula(self):
        """CD = 0.02 + 0.5²/(π×8×0.9) = 0.02 + 0.01105 ≈ 0.03105."""
        r = total_drag_coefficient(CD0=0.02, CL=0.5, AR=8.0, e=0.9)
        assert r["ok"] is True
        cdi = 0.25 / (math.pi * 8.0 * 0.9)
        assert _rel_close(r["CD"], 0.02 + cdi)
        assert _rel_close(r["CDi"], cdi)

    def test_ld_ratio(self):
        """L/D = CL/CD = 0.5/0.03 = 16.67."""
        r = ld_ratio(CL=0.5, CD=0.03)
        assert r["ok"] is True
        assert _rel_close(r["LD"], 0.5 / 0.03)

    def test_ld_zero_cd_error(self):
        """CD=0 should return ok=False."""
        r = ld_ratio(CL=0.5, CD=0.0)
        assert r["ok"] is False

    def test_best_glide_cl(self):
        """
        CD0=0.02, AR=8, e=1:
          CL_best = √(π×8×0.02) = √0.5027 ≈ 0.7090
          (L/D)_max = CL_best / (2 × 0.02) = 0.7090/0.04 ≈ 17.72
        Anderson, Intro to Flight ch.5.
        """
        r = best_glide_cl(CD0=0.02, AR=8.0, e=1.0)
        assert r["ok"] is True
        expected_CL = math.sqrt(math.pi * 8.0 * 1.0 * 0.02)
        assert _rel_close(r["CL_best"], expected_CL)
        assert _rel_close(r["LD_max"], expected_CL / (2.0 * 0.02))


# ===========================================================================
# 9. Level-flight performance
# ===========================================================================

class TestLevelFlight:

    def test_thrust_required(self):
        """T = W × CD/CL = 50 000 × 0.03/0.4 = 3750 N."""
        r = level_flight_thrust(W=50_000.0, CL=0.4, CD=0.03)
        assert r["ok"] is True
        assert _rel_close(r["T_req_N"], 50_000.0 * 0.03 / 0.4)

    def test_power_required(self):
        """P = T × V = 3750 × 80 = 300 000 W."""
        r = level_flight_power(T=3750.0, V=80.0)
        assert r["ok"] is True
        assert _rel_close(r["P_req_W"], 300_000.0)

    def test_stall_speed_formula(self):
        """
        W=50 000 N, ρ=1.225, S=20 m², CLmax=1.4:
          V_stall = √(2×50000/(1.225×20×1.4)) = √(100000/34.3) ≈ 54.01 m/s.
        """
        r = stall_speed(W=50_000.0, rho=1.225, S=20.0, CLmax=1.4)
        assert r["ok"] is True
        expected = math.sqrt(2 * 50_000.0 / (1.225 * 20.0 * 1.4))
        assert _rel_close(r["V_stall_m_s"], expected)

    def test_negative_weight_error(self):
        """W < 0 → ok=False."""
        r = level_flight_thrust(W=-1.0, CL=0.4, CD=0.03)
        assert r["ok"] is False

    def test_stall_scales_inversely_with_density(self):
        """Higher altitude (lower ρ) → higher stall speed."""
        r_sl = stall_speed(W=20_000.0, rho=1.225, S=15.0, CLmax=1.3)
        r_hi = stall_speed(W=20_000.0, rho=0.8, S=15.0, CLmax=1.3)
        assert r_hi["V_stall_m_s"] > r_sl["V_stall_m_s"]


# ===========================================================================
# 10. Climb rate
# ===========================================================================

class TestClimbRate:

    def test_positive_climb(self):
        """RC = (T−D)V/W = (5000−3000)×80/50000 = 3.2 m/s."""
        r = climb_rate(T=5000.0, D=3000.0, V=80.0, W=50_000.0)
        assert r["ok"] is True
        assert _rel_close(r["RC_m_s"], 3.2)
        assert r["negative_climb"] is False

    def test_zero_excess_thrust(self):
        """T=D → RC=0, negative_climb=True."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            r = climb_rate(T=3000.0, D=3000.0, V=80.0, W=50_000.0)
        assert r["ok"] is True
        assert r["RC_m_s"] == 0.0
        assert r["negative_climb"] is True
        assert any("non-positive" in str(x.message).lower() for x in w)

    def test_negative_climb_warning(self):
        """T < D → RC < 0, warning issued."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            r = climb_rate(T=2000.0, D=3500.0, V=80.0, W=50_000.0)
        assert r["negative_climb"] is True
        assert any("non-positive" in str(x.message).lower() for x in w)


# ===========================================================================
# 11. Actuator disc / propeller
# ===========================================================================

class TestActuatorDisc:

    def test_static_thrust_formula(self):
        """
        V_inf=0, w=10 m/s, ρ=1.225, A=0.5 m²:
          T = 2 × 1.225 × 0.5 × (0+10) × 10 = 122.5 N.
        """
        r = actuator_disc_thrust(rho=1.225, A_disc=0.5, V_inf=0.0, w=10.0)
        assert r["ok"] is True
        assert _rel_close(r["T_N"], 122.5)

    def test_forward_flight_thrust(self):
        """
        V_inf=50, w=5, ρ=1.225, A=0.5:
          T = 2 × 1.225 × 0.5 × 55 × 5 = 336.875 N.
        """
        r = actuator_disc_thrust(rho=1.225, A_disc=0.5, V_inf=50.0, w=5.0)
        assert r["ok"] is True
        expected = 2.0 * 1.225 * 0.5 * 55.0 * 5.0
        assert _rel_close(r["T_N"], expected)

    def test_ideal_efficiency(self):
        """V_inf=50, w=5: η = 50/55 ≈ 0.9091."""
        r = propeller_ideal_efficiency(V_inf=50.0, w=5.0)
        assert r["ok"] is True
        assert _rel_close(r["eta_ideal"], 50.0 / 55.0)

    def test_static_efficiency_zero(self):
        """V_inf=0 → η=0, static_thrust_note=True."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            r = propeller_ideal_efficiency(V_inf=0.0, w=10.0)
        assert r["ok"] is True
        assert r["eta_ideal"] == 0.0
        assert r["static_thrust_note"] is True
        assert any("static" in str(x.message).lower() for x in w)

    def test_efficiency_between_0_and_1(self):
        """Efficiency must be in (0, 1) for V_inf > 0."""
        r = propeller_ideal_efficiency(V_inf=30.0, w=5.0)
        assert 0.0 < r["eta_ideal"] < 1.0

    def test_efficiency_increases_with_speed(self):
        """Higher V_inf at same induced velocity → higher efficiency."""
        r1 = propeller_ideal_efficiency(V_inf=20.0, w=5.0)
        r2 = propeller_ideal_efficiency(V_inf=50.0, w=5.0)
        assert r2["eta_ideal"] > r1["eta_ideal"]


# ===========================================================================
# 12. Breguet range and endurance
# ===========================================================================

class TestBreguet:

    def test_range_formula(self):
        """
        Anderson, Intro to Flight, Example 6.6 style:
        η_p=0.8, c=8e-8 kg/(N·s), L/D=15, W_i=50 000 N, W_f=35 000 N:
          R = (0.8/8e-8) × 15 × ln(50000/35000)
            = 1e7 × 15 × 0.35667
            ≈ 53 500 590 m ≈ 53 501 km  (sanity: long-haul turboprop ballpark)
        """
        r = breguet_range(
            eta_p=0.8,
            c_specific=8e-8,
            LD=15.0,
            W_initial=50_000.0,
            W_final=35_000.0,
        )
        assert r["ok"] is True
        expected = (0.8 / 8e-8) * 15.0 * math.log(50_000.0 / 35_000.0)
        assert _rel_close(r["range_m"], expected)

    def test_endurance_formula(self):
        """
        Breguet endurance: E = (η_p/c)(CL/CD)(1/g) ln(W_i/W_f).
        η_p=0.8, c=8e-8, CL=0.8, CD=0.05 (L/D=16), W_i=50000, W_f=40000, g=9.80665.
        """
        r = breguet_endurance(
            eta_p=0.8,
            c_specific=8e-8,
            CL=0.8,
            CD=0.05,
            W_initial=50_000.0,
            W_final=40_000.0,
        )
        assert r["ok"] is True
        g = 9.80665
        expected = (0.8 / 8e-8) * (0.8 / 0.05) * (1.0 / g) * math.log(50_000.0 / 40_000.0)
        assert _rel_close(r["endurance_s"], expected)

    def test_range_requires_fuel(self):
        """W_initial <= W_final should return ok=False."""
        r = breguet_range(
            eta_p=0.8,
            c_specific=8e-8,
            LD=15.0,
            W_initial=30_000.0,
            W_final=30_000.0,
        )
        assert r["ok"] is False

    def test_range_increases_with_ld(self):
        """Higher L/D → longer range."""
        r1 = breguet_range(
            eta_p=0.8, c_specific=8e-8, LD=12.0,
            W_initial=50_000.0, W_final=35_000.0,
        )
        r2 = breguet_range(
            eta_p=0.8, c_specific=8e-8, LD=18.0,
            W_initial=50_000.0, W_final=35_000.0,
        )
        assert r2["range_m"] > r1["range_m"]

    def test_endurance_km_conversion(self):
        """range_km = range_m / 1000."""
        r = breguet_range(
            eta_p=0.75, c_specific=9e-8, LD=14.0,
            W_initial=40_000.0, W_final=28_000.0,
        )
        assert _rel_close(r["range_km"], r["range_m"] / 1000.0)

    def test_endurance_hr_conversion(self):
        """endurance_hr = endurance_s / 3600."""
        r = breguet_endurance(
            eta_p=0.75, c_specific=9e-8, CL=0.7, CD=0.045,
            W_initial=40_000.0, W_final=28_000.0,
        )
        assert _rel_close(r["endurance_hr"], r["endurance_s"] / 3600.0)


# ===========================================================================
# 13. ISA at 11 km — full Anderson hand-calc cross-check
# ===========================================================================

class TestISA11km:
    """
    Cross-check against Anderson, Introduction to Flight, Appendix A:
    At h = 11 000 m (geopotential):
      T   = 216.65 K
      p   = 22 632.1 Pa
      ρ   = 0.36392 kg/m³
      a   = √(1.4 × 287.05 × 216.65) ≈ 295.07 m/s
    """

    def setup_method(self):
        self.r = isa_atmosphere(11_000.0)

    def test_ok(self):
        assert self.r["ok"] is True

    def test_temperature(self):
        assert _rel_close(self.r["T_K"], 216.65, tol=1e-4)

    def test_pressure(self):
        assert _rel_close(self.r["p_Pa"], 22_632.1, tol=1e-3)

    def test_density(self):
        assert _rel_close(self.r["rho_kg_m3"], 0.36392, tol=1e-3)

    def test_speed_of_sound(self):
        a_expected = math.sqrt(1.4 * 287.05287 * 216.65)
        assert _rel_close(self.r["a_m_s"], a_expected, tol=1e-4)


# ===========================================================================
# AUTHORITATIVE EXTERNAL REFERENCE CASES
# ---------------------------------------------------------------------------
# Cross-checked against the ICAO Standard Atmosphere (ICAO Doc 7488, 3rd ed.)
# and Anderson, "Introduction to Flight" 8th ed. / "Fundamentals of
# Aerodynamics" 6th ed.
# ===========================================================================

class TestAeroAuthoritativeReferences:
    def test_isa_sea_level_icao(self):
        # ICAO Doc 7488: T0=288.15 K, p0=101325 Pa, rho0=1.225 kg/m3.
        r = isa_atmosphere(0.0)
        assert r["T_K"] == pytest.approx(288.15, abs=1e-6)
        assert r["p_Pa"] == pytest.approx(101325.0, abs=1e-3)
        assert r["rho_kg_m3"] == pytest.approx(1.225, abs=1e-4)

    def test_isa_sea_level_sound_speed(self):
        # ICAO ISA sea-level speed of sound = 340.294 m/s.
        r = isa_atmosphere(0.0)
        assert r["a_m_s"] == pytest.approx(340.294, abs=0.01)

    def test_isa_11km_tropopause_icao(self):
        # ICAO Doc 7488 at 11 000 m (tropopause): T=216.65 K, p=22632 Pa,
        # rho=0.36392 kg/m3.
        r = isa_atmosphere(11_000.0)
        assert r["T_K"] == pytest.approx(216.65, abs=1e-2)
        assert r["p_Pa"] == pytest.approx(22632.0, abs=1.0)
        assert r["rho_kg_m3"] == pytest.approx(0.36392, abs=1e-4)

    def test_isa_5km_icao(self):
        # ICAO Doc 7488 at 5 000 m: T=255.65 K, p=54019.9 Pa, rho=0.73612.
        r = isa_atmosphere(5000.0)
        assert r["T_K"] == pytest.approx(255.65, abs=1e-2)
        assert r["p_Pa"] == pytest.approx(54019.9, abs=2.0)
        assert r["rho_kg_m3"] == pytest.approx(0.73612, abs=1e-3)

    def test_thin_airfoil_lift_slope_2pi(self):
        # Thin-airfoil theory (Anderson FoA 6e, Ch.4): dCl/dalpha = 2*pi per rad
        # => Cl at 1 rad (alpha0=0) is 2*pi.
        r = thin_airfoil_cl(1.0, 0.0)
        assert r["Cl"] == pytest.approx(2.0 * math.pi, rel=1e-9)

    def test_prandtl_glauert_known(self):
        # Anderson FoA: beta = sqrt(1-M^2). At M=0.6 -> 0.8.
        r = prandtl_glauert_factor(0.6)
        assert r["beta"] == pytest.approx(0.8, abs=1e-9)

    def test_finite_wing_slope_AR_infinite_limit(self):
        # Prandtl lifting-line: as AR->inf, a -> a0 = 2*pi.
        r = finite_wing_lift_slope(a0=2.0 * math.pi, AR=1e6, e_planform=1.0)
        assert r["a_rad_inv"] == pytest.approx(2.0 * math.pi, rel=1e-4)

    def test_induced_drag_elliptic(self):
        # Anderson: CDi = CL^2/(pi*AR*e). CL=1, AR=8, e=1 -> 0.0398.
        r = induced_drag_coefficient(1.0, 8.0, 1.0)
        assert r["CDi"] == pytest.approx(1.0 / (math.pi * 8.0), rel=1e-9)

    def test_best_glide_condition(self):
        # Max L/D occurs when CDi = CD0 -> CL* = sqrt(pi*AR*e*CD0).
        r = best_glide_cl(CD0=0.02, AR=10.0, e=0.85)
        assert r["CL_best"] == pytest.approx(
            math.sqrt(math.pi * 10.0 * 0.85 * 0.02), rel=1e-9)
        # (L/D)max = CL*/(2*CD0)
        assert r["LD_max"] == pytest.approx(r["CL_best"] / (2.0 * 0.02), rel=1e-9)

    def test_breguet_range_textbook(self):
        # Breguet propeller range R = (eta/c)(L/D)ln(Wi/Wf). Anderson Ch.6
        # eta=0.85, c=8e-7 1/m, L/D=15, Wi/Wf=1.5 -> R = 0.85/8e-7*15*ln1.5
        r = breguet_range(0.85, 8e-7, 15.0, 1.5e5, 1.0e5)
        expected = (0.85 / 8e-7) * 15.0 * math.log(1.5)
        assert r["range_m"] == pytest.approx(expected, rel=1e-9)
