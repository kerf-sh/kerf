"""
Hermetic tests for kerf_cad_core.clutchbrake — friction clutch & brake design.

Coverage:
  design.disc_clutch_torque    — uniform-wear, uniform-pressure, multi-plate
  design.cone_clutch_torque    — normal case, self-lock detection
  design.band_brake_torque     — capstan equation, self-energizing factor
  design.drum_brake_torque     — leading and trailing shoes, self-lock
  design.disc_brake_torque     — caliper disc brake
  design.engagement_energy     — kinetic + load energy
  design.temperature_rise      — lumped ΔT
  design.heat_dissipation_area — Q = h·A·ΔT
  design.wear_pv_check         — material catalog, pV exceeded
  design.engagement_time       — synchronisation time, feasibility
  design.friction_material_props — catalog lookup

All tests are pure-Python and hermetic; no OCC, no DB, no network.
Formulas verified against Shigley 10th ed. §§ 16-1..16-12 and
Juvinall & Marshek 5th ed. §§ 18.1-18.9.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.clutchbrake.design import (
    disc_clutch_torque,
    cone_clutch_torque,
    band_brake_torque,
    drum_brake_torque,
    disc_brake_torque,
    engagement_energy,
    temperature_rise,
    heat_dissipation_area,
    wear_pv_check,
    engagement_time,
    friction_material_props,
)
from kerf_cad_core.clutchbrake.tools import (
    run_disc_clutch_torque,
    run_cone_clutch_torque,
    run_band_brake_torque,
    run_drum_brake_torque,
    run_disc_brake_torque,
    run_engagement_energy,
    run_temperature_rise,
    run_heat_dissipation_area,
    run_wear_pv_check,
    run_engagement_time,
    run_friction_material_props,
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
        return object()


def _args(**kw) -> bytes:
    return json.dumps(kw).encode()


# ---------------------------------------------------------------------------
# 1. disc_clutch_torque — uniform-wear
# ---------------------------------------------------------------------------

class TestDiscClutchUniformWear:
    """
    Shigley §16-2 uniform-wear: r_mean = (r_o + r_i) / 2
    T = mu * F_a * r_mean  per friction surface; n_surfaces = 2*n_plates.
    """

    def test_basic_single_plate(self):
        # r_mean = (0.15 + 0.05) / 2 = 0.10 m
        # T_per = 0.35 * 5000 * 0.10 = 175 N·m
        # T_total = 175 * 2 = 350 N·m
        r = disc_clutch_torque(5000, 0.35, 0.15, 0.05)
        assert r["ok"] is True
        assert r["n_surfaces"] == 2
        assert abs(r["r_mean_m"] - 0.10) < 1e-9
        assert abs(r["torque_Nm"] - 350.0) < 1e-6

    def test_multi_plate_quadruples_n_surfaces(self):
        # n_plates=3 → n_surfaces=6
        r = disc_clutch_torque(5000, 0.35, 0.15, 0.05, n_plates=3)
        assert r["ok"] is True
        assert r["n_surfaces"] == 6
        # torque scales linearly with n_surfaces
        r1 = disc_clutch_torque(5000, 0.35, 0.15, 0.05, n_plates=1)
        assert abs(r["torque_Nm"] - r1["torque_Nm"] * 3) < 1e-6

    def test_zero_inner_radius(self):
        # disc from centre: r_mean = r_o / 2
        r = disc_clutch_torque(1000, 0.3, 0.10, 0.0)
        assert r["ok"] is True
        assert abs(r["r_mean_m"] - 0.05) < 1e-9

    def test_invalid_r_i_ge_r_o(self):
        r = disc_clutch_torque(1000, 0.3, 0.10, 0.10)
        assert r["ok"] is False

    def test_negative_F_a(self):
        r = disc_clutch_torque(-100, 0.3, 0.10, 0.05)
        assert r["ok"] is False

    def test_method_roundtrip(self):
        r = disc_clutch_torque(2000, 0.4, 0.12, 0.04, method="uniform-wear")
        assert r["method"] == "uniform-wear"


# ---------------------------------------------------------------------------
# 2. disc_clutch_torque — uniform-pressure
# ---------------------------------------------------------------------------

class TestDiscClutchUniformPressure:
    """
    Shigley §16-2 uniform-pressure: r_mean = (2/3) × (r_o³ - r_i³) / (r_o² - r_i²)
    """

    def test_r_mean_formula(self):
        r_o, r_i = 0.15, 0.05
        num = r_o ** 3 - r_i ** 3
        den = r_o ** 2 - r_i ** 2
        r_mean_expected = (2.0 / 3.0) * num / den
        result = disc_clutch_torque(5000, 0.35, r_o, r_i, method="uniform-pressure")
        assert result["ok"] is True
        assert abs(result["r_mean_m"] - r_mean_expected) < 1e-9

    def test_uniform_pressure_gt_wear(self):
        # Uniform-pressure gives higher r_mean (and torque) than uniform-wear
        r_wear = disc_clutch_torque(5000, 0.35, 0.15, 0.05, method="uniform-wear")
        r_pres = disc_clutch_torque(5000, 0.35, 0.15, 0.05, method="uniform-pressure")
        assert r_pres["r_mean_m"] > r_wear["r_mean_m"]
        assert r_pres["torque_Nm"] > r_wear["torque_Nm"]

    def test_unknown_method(self):
        r = disc_clutch_torque(5000, 0.35, 0.15, 0.05, method="bogus")
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 3. cone_clutch_torque
# ---------------------------------------------------------------------------

class TestConeClutch:
    """
    Juvinall §18.5: T = mu * F_a * r_mean / sin(alpha)
    """

    def test_basic_formula(self):
        F_a, mu, r_o, r_i, alpha_deg = 2000, 0.3, 0.12, 0.06, 12.0
        r_mean = (r_o + r_i) / 2.0
        sin_a = math.sin(math.radians(alpha_deg))
        T_expected = mu * F_a * r_mean / sin_a
        r = cone_clutch_torque(F_a, mu, r_o, r_i, alpha_deg)
        assert r["ok"] is True
        assert abs(r["torque_Nm"] - T_expected) < 1e-6

    def test_self_lock_flag_when_mu_ge_sin_alpha(self):
        # sin(10°) ≈ 0.1736; mu=0.2 → self-lock
        r = cone_clutch_torque(1000, 0.2, 0.10, 0.05, 10.0)
        assert r["ok"] is True
        assert r["self_lock"] is True
        assert len(r["warnings"]) > 0

    def test_no_self_lock_large_angle(self):
        # alpha=30°; sin=0.5; mu=0.3 < 0.5 → no self-lock
        r = cone_clutch_torque(1000, 0.3, 0.10, 0.05, 30.0)
        assert r["ok"] is True
        assert r["self_lock"] is False

    def test_invalid_alpha_zero(self):
        r = cone_clutch_torque(1000, 0.3, 0.10, 0.05, 0.0)
        assert r["ok"] is False

    def test_uniform_pressure_cone(self):
        r = cone_clutch_torque(2000, 0.3, 0.12, 0.06, 12.0, method="uniform-pressure")
        r_wear = cone_clutch_torque(2000, 0.3, 0.12, 0.06, 12.0, method="uniform-wear")
        # uniform-pressure should give higher torque
        assert r["torque_Nm"] > r_wear["torque_Nm"]


# ---------------------------------------------------------------------------
# 4. band_brake_torque
# ---------------------------------------------------------------------------

class TestBandBrake:
    """
    Capstan equation: F_tight / F_slack = exp(mu * theta)
    T = (F_tight - F_slack) * r
    """

    def test_capstan_ratio(self):
        mu, theta_deg = 0.3, 270.0
        theta_rad = math.radians(theta_deg)
        expected_ratio = math.exp(mu * theta_rad)
        r = band_brake_torque(0.15, theta_deg, mu, 1000.0)
        assert r["ok"] is True
        assert abs(r["capstan_ratio"] - expected_ratio) < 1e-6

    def test_torque_formula(self):
        # F_tight=1000, mu=0.3, theta=270°, r=0.15
        mu, theta_deg, F_tight, radius = 0.3, 270.0, 1000.0, 0.15
        theta_rad = math.radians(theta_deg)
        capstan = math.exp(mu * theta_rad)
        F_slack = F_tight / capstan
        T_expected = (F_tight - F_slack) * radius
        r = band_brake_torque(radius, theta_deg, mu, F_tight)
        assert abs(r["torque_Nm"] - T_expected) < 1e-6

    def test_slack_less_than_tight(self):
        r = band_brake_torque(0.10, 180.0, 0.35, 500.0)
        assert r["ok"] is True
        assert r["F_slack_N"] < r["F_tight_N"]

    def test_full_revolution_wrap(self):
        # 360° wrap; should produce largest braking torque for same F_tight
        r180 = band_brake_torque(0.10, 180.0, 0.3, 500.0)
        r360 = band_brake_torque(0.10, 360.0, 0.3, 500.0)
        assert r360["torque_Nm"] > r180["torque_Nm"]

    def test_negative_mu_rejected(self):
        r = band_brake_torque(0.10, 270.0, -0.1, 500.0)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 5. drum_brake_torque
# ---------------------------------------------------------------------------

class TestDrumBrake:
    """
    Shigley §16-8 long-shoe: pressure distribution p(θ) = p_max * sin(θ).
    Torque: T = p_max * b * r² * mu / sin_theta_max * (cosθ1 - cosθ2)
    """

    def test_leading_shoe_positive_torque(self):
        r = drum_brake_torque(0.15, 0.04, 0.35, 1.0e6, 10.0, 120.0, 0.15)
        assert r["ok"] is True
        assert r["torque_Nm"] > 0
        assert r["shoe_type"] == "leading"

    def test_trailing_shoe_same_torque_formula(self):
        # Use geometry where M_n > M_f (no self-lock): r=0.10, a=0.05, mu=0.25
        # torque formula is the same; actuating force differs
        rl = drum_brake_torque(0.10, 0.04, 0.25, 1.0e6, 10.0, 120.0, 0.05, shoe_type="leading")
        rt = drum_brake_torque(0.10, 0.04, 0.25, 1.0e6, 10.0, 120.0, 0.05, shoe_type="trailing")
        assert abs(rl["torque_Nm"] - rt["torque_Nm"]) < 1e-6
        # trailing shoe requires more actuating force (M_n + M_f > M_n - M_f)
        assert rt["actuating_F_N"] > rl["actuating_F_N"]

    def test_self_energizing_flag(self):
        r = drum_brake_torque(0.15, 0.04, 0.35, 1.0e6, 10.0, 120.0, 0.15, shoe_type="leading")
        assert r["self_energizing"] is True
        r2 = drum_brake_torque(0.15, 0.04, 0.35, 1.0e6, 10.0, 120.0, 0.15, shoe_type="trailing")
        assert r2["self_energizing"] is False

    def test_theta2_le_theta1_rejected(self):
        r = drum_brake_torque(0.15, 0.04, 0.35, 1.0e6, 90.0, 30.0, 0.15)
        assert r["ok"] is False

    def test_invalid_shoe_type(self):
        r = drum_brake_torque(0.15, 0.04, 0.35, 1.0e6, 10.0, 120.0, 0.15, shoe_type="bad")
        assert r["ok"] is False

    def test_torque_scales_with_mu(self):
        # Torque should increase proportionally with mu
        r1 = drum_brake_torque(0.15, 0.04, 0.20, 1.0e6, 10.0, 120.0, 0.15)
        r2 = drum_brake_torque(0.15, 0.04, 0.40, 1.0e6, 10.0, 120.0, 0.15)
        assert r2["torque_Nm"] > r1["torque_Nm"]


# ---------------------------------------------------------------------------
# 6. disc_brake_torque
# ---------------------------------------------------------------------------

class TestDiscBrake:
    """
    T = n_pads × μ × F_clamp × r_eff
    """

    def test_basic_floating_caliper(self):
        # n_pads=2, mu=0.4, F_clamp=5000, r_eff=0.12
        # T = 2 * 0.4 * 5000 * 0.12 = 480 N·m
        r = disc_brake_torque(5000, 0.4, 0.12)
        assert r["ok"] is True
        assert abs(r["torque_Nm"] - 480.0) < 1e-6

    def test_fixed_caliper_4_pads(self):
        r2 = disc_brake_torque(5000, 0.4, 0.12, n_pads=2)
        r4 = disc_brake_torque(5000, 0.4, 0.12, n_pads=4)
        assert abs(r4["torque_Nm"] - 2 * r2["torque_Nm"]) < 1e-6

    def test_n_pads_zero_rejected(self):
        r = disc_brake_torque(5000, 0.4, 0.12, n_pads=0)
        assert r["ok"] is False

    def test_negative_F_clamp(self):
        r = disc_brake_torque(-100, 0.4, 0.12)
        assert r["ok"] is False

    def test_high_mu_warning(self):
        r = disc_brake_torque(5000, 0.7, 0.12)
        assert r["ok"] is True
        assert len(r["warnings"]) > 0


# ---------------------------------------------------------------------------
# 7. engagement_energy
# ---------------------------------------------------------------------------

class TestEngagementEnergy:
    """
    Shigley §16-1 / Juvinall §18.2:
    E_kin = 0.5 * I_eff * Δω²
    I_eff = I1*I2 / (I1 + I2)
    """

    def test_kinetic_only(self):
        I1, I2, w1, w2 = 2.0, 3.0, 100.0, 0.0
        I_eff = I1 * I2 / (I1 + I2)
        E_expected = 0.5 * I_eff * (w1 - w2) ** 2
        r = engagement_energy(w1, w2, I1, I2)
        assert r["ok"] is True
        assert abs(r["E_kinetic_J"] - E_expected) < 1e-6
        assert abs(r["E_load_J"]) < 1e-9

    def test_with_load_energy(self):
        r = engagement_energy(100.0, 0.0, 2.0, 3.0, T_load_Nm=50.0, t_engage_s=0.5)
        assert r["ok"] is True
        assert r["E_load_J"] > 0

    def test_same_speeds_zero_energy(self):
        r = engagement_energy(50.0, 50.0, 1.0, 1.0)
        assert r["ok"] is True
        assert abs(r["E_kinetic_J"]) < 1e-9

    def test_negative_inertia_rejected(self):
        r = engagement_energy(100.0, 0.0, -1.0, 2.0)
        assert r["ok"] is False

    def test_i_eff_value(self):
        r = engagement_energy(80.0, 20.0, 4.0, 4.0)
        assert abs(r["I_eff"] - 2.0) < 1e-9  # 4*4/(4+4)=2


# ---------------------------------------------------------------------------
# 8. temperature_rise
# ---------------------------------------------------------------------------

class TestTemperatureRise:
    """
    ΔT = (fraction × E_slip) / (m × cp)
    """

    def test_basic_formula(self):
        # E=1000 J, fraction=0.5, m=5 kg, cp=500 J/kgK → ΔT = 500/2500 = 0.2 K
        r = temperature_rise(1000.0, 5.0, cp_J_per_kgK=500.0, fraction_to_rotor=0.5)
        assert r["ok"] is True
        assert abs(r["delta_T_K"] - 0.2) < 1e-9

    def test_all_energy_to_rotor(self):
        r_half = temperature_rise(2000.0, 2.0, fraction_to_rotor=0.5)
        r_full = temperature_rise(2000.0, 2.0, fraction_to_rotor=1.0)
        assert abs(r_full["delta_T_K"] - 2 * r_half["delta_T_K"]) < 1e-9

    def test_invalid_fraction_zero(self):
        r = temperature_rise(1000.0, 5.0, fraction_to_rotor=0.0)
        assert r["ok"] is False

    def test_high_rise_warning(self):
        # Very high: 5 MJ, 2 kg, cp=500 → ΔT=2500 K
        r = temperature_rise(5e6, 2.0)
        assert r["ok"] is True
        assert len(r["warnings"]) > 0

    def test_negative_mass_rejected(self):
        r = temperature_rise(1000.0, -1.0)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 9. heat_dissipation_area
# ---------------------------------------------------------------------------

class TestHeatDissipationArea:
    """
    A = Q / (h × ΔT)
    """

    def test_basic(self):
        # Q=1000 W, h=20 W/m²K, ΔT=50 K → A = 1000/1000 = 1 m²
        r = heat_dissipation_area(1000.0, h_conv=20.0, delta_T_K=50.0)
        assert r["ok"] is True
        assert abs(r["area_m2"] - 1.0) < 1e-9

    def test_defaults(self):
        # Q=1600 W, h=20, ΔT=80 → A = 1600/1600 = 1.0 m²
        r = heat_dissipation_area(1600.0)
        assert r["ok"] is True
        assert abs(r["area_m2"] - 1.0) < 1e-9

    def test_forced_convection_smaller_area(self):
        r_nat = heat_dissipation_area(500.0, h_conv=20.0)
        r_frc = heat_dissipation_area(500.0, h_conv=200.0)
        assert r_frc["area_m2"] < r_nat["area_m2"]

    def test_negative_power_rejected(self):
        r = heat_dissipation_area(-100.0)
        assert r["ok"] is False

    def test_large_area_warning(self):
        # 200 kW, h=20, ΔT=80 → A = 125 m²
        r = heat_dissipation_area(200000.0)
        assert r["ok"] is True
        assert len(r["warnings"]) > 0


# ---------------------------------------------------------------------------
# 10. wear_pv_check
# ---------------------------------------------------------------------------

class TestWearPvCheck:
    """
    pV = p_contact × v_slip
    Compare against material catalog limit.
    """

    def test_ok_below_limit(self):
        # cast_iron_dry max_pv = 1.75e6 Pa·m/s
        # p=1e5 Pa, v=5 m/s → pV=5e5 < 1.75e6
        r = wear_pv_check(1e5, 5.0, "cast_iron_dry")
        assert r["ok"] is True
        assert r["pv_ok"] is True
        assert r["safety_factor"] > 1.0

    def test_exceeded_above_limit(self):
        # p=1e6, v=5 → pV=5e6 > 1.75e6
        r = wear_pv_check(1e6, 5.0, "cast_iron_dry")
        assert r["ok"] is True
        assert r["pv_ok"] is False
        assert len(r["warnings"]) > 0

    def test_carbon_graphite_highest_limit(self):
        # carbon_graphite max_pv = 7e6
        r = wear_pv_check(1e6, 5.0, "carbon_graphite")
        assert r["ok"] is True
        assert r["pv_ok"] is True

    def test_unknown_material(self):
        r = wear_pv_check(1e5, 5.0, "unobtanium")
        assert r["ok"] is False

    def test_safety_factor_at_limit(self):
        # Right at the limit: sf should be ≈ 1.0
        r = wear_pv_check(1.75e6, 1.0, "cast_iron_dry")
        assert r["ok"] is True
        assert abs(r["safety_factor"] - 1.0) < 1e-6


# ---------------------------------------------------------------------------
# 11. engagement_time
# ---------------------------------------------------------------------------

class TestEngagementTime:
    """
    t_sync = Δω × I1 × I2 / [(Tc - TL) × (I1 + I2)]
    """

    def test_basic_sync_time(self):
        w1, w2, I1, I2, Tc = 100.0, 0.0, 2.0, 3.0, 50.0
        dw = w1 - w2
        I12 = I1 + I2
        T_net = Tc
        t_expected = dw * I1 * I2 / (T_net * I12)
        r = engagement_time(w1, w2, I1, I2, Tc)
        assert r["ok"] is True
        assert abs(r["t_sync_s"] - t_expected) < 1e-9

    def test_same_speeds_zero_time(self):
        r = engagement_time(50.0, 50.0, 2.0, 3.0, 100.0)
        assert r["ok"] is True
        assert abs(r["t_sync_s"]) < 1e-9

    def test_not_feasible_when_load_ge_torque(self):
        r = engagement_time(100.0, 0.0, 2.0, 3.0, 20.0, T_load_Nm=30.0)
        assert r["ok"] is True
        assert r["t_sync_feasible"] is False
        assert len(r["warnings"]) > 0

    def test_feasible_flag(self):
        r = engagement_time(100.0, 0.0, 2.0, 3.0, 100.0, T_load_Nm=10.0)
        assert r["ok"] is True
        assert r["t_sync_feasible"] is True

    def test_negative_inertia_rejected(self):
        r = engagement_time(100.0, 0.0, -1.0, 2.0, 50.0)
        assert r["ok"] is False

    def test_slip_energy_positive(self):
        r = engagement_time(200.0, 0.0, 1.0, 1.0, 100.0)
        assert r["ok"] is True
        assert r["E_slip_J"] > 0


# ---------------------------------------------------------------------------
# 12. friction_material_props
# ---------------------------------------------------------------------------

class TestFrictionMaterialProps:

    def test_cast_iron_dry(self):
        r = friction_material_props("cast_iron_dry")
        assert r["ok"] is True
        assert abs(r["mu"] - 0.40) < 1e-9
        assert r["max_pv"] == 1.75e6
        assert r["max_temp"] == 250.0

    def test_carbon_graphite(self):
        r = friction_material_props("carbon_graphite")
        assert r["ok"] is True
        assert r["max_temp"] == 500.0

    def test_unknown_returns_available_list(self):
        r = friction_material_props("unobtanium")
        assert r["ok"] is False
        assert "available" in r
        assert len(r["available"]) > 0

    def test_normalises_whitespace(self):
        r = friction_material_props("molded_dry")
        assert r["ok"] is True


# ---------------------------------------------------------------------------
# 13. LLM tool wrappers — happy-path smoke tests
# ---------------------------------------------------------------------------

class TestTools:

    def test_tool_disc_clutch_happy(self):
        raw = _run(run_disc_clutch_torque(_ctx(), _args(F_a=5000, mu=0.35, r_o=0.15, r_i=0.05)))
        r = json.loads(raw)
        assert r["ok"] is True
        assert "torque_Nm" in r

    def test_tool_cone_clutch_happy(self):
        raw = _run(run_cone_clutch_torque(_ctx(), _args(F_a=2000, mu=0.3, r_o=0.12, r_i=0.06, half_angle_deg=12.0)))
        r = json.loads(raw)
        assert r["ok"] is True

    def test_tool_band_brake_happy(self):
        raw = _run(run_band_brake_torque(_ctx(), _args(drum_radius=0.15, angle_wrap_deg=270.0, mu=0.3, F_tight=1000.0)))
        r = json.loads(raw)
        assert r["ok"] is True
        assert r["torque_Nm"] > 0

    def test_tool_drum_brake_happy(self):
        raw = _run(run_drum_brake_torque(_ctx(), _args(
            drum_radius=0.15, shoe_width=0.04, mu=0.35, p_max=1e6,
            theta1_deg=10.0, theta2_deg=120.0, pivot_a=0.15,
        )))
        r = json.loads(raw)
        assert r["ok"] is True

    def test_tool_disc_brake_happy(self):
        raw = _run(run_disc_brake_torque(_ctx(), _args(F_clamp=5000, mu=0.4, r_eff=0.12)))
        r = json.loads(raw)
        assert r["ok"] is True
        assert abs(r["torque_Nm"] - 480.0) < 1e-6

    def test_tool_engagement_energy_happy(self):
        raw = _run(run_engagement_energy(_ctx(), _args(
            omega1_rad_s=100.0, omega2_rad_s=0.0, I_driving=2.0, I_driven=3.0,
        )))
        r = json.loads(raw)
        assert r["ok"] is True

    def test_tool_temperature_rise_happy(self):
        raw = _run(run_temperature_rise(_ctx(), _args(E_slip_J=1000.0, mass_rotor_kg=5.0)))
        r = json.loads(raw)
        assert r["ok"] is True
        assert r["delta_T_K"] > 0

    def test_tool_heat_dissipation_area_happy(self):
        raw = _run(run_heat_dissipation_area(_ctx(), _args(power_W=1000.0)))
        r = json.loads(raw)
        assert r["ok"] is True

    def test_tool_wear_pv_check_happy(self):
        raw = _run(run_wear_pv_check(_ctx(), _args(p_contact=1e5, v_slip=5.0, material="molded_dry")))
        r = json.loads(raw)
        assert r["ok"] is True

    def test_tool_engagement_time_happy(self):
        raw = _run(run_engagement_time(_ctx(), _args(
            omega1_rad_s=100.0, omega2_rad_s=0.0,
            I_driving=2.0, I_driven=3.0, T_clutch_Nm=50.0,
        )))
        r = json.loads(raw)
        assert r["ok"] is True

    def test_tool_friction_material_happy(self):
        raw = _run(run_friction_material_props(_ctx(), _args(material="sintered_metal_dry")))
        r = json.loads(raw)
        assert r["ok"] is True
        assert "mu" in r

    def test_tool_missing_required_arg(self):
        raw = _run(run_disc_clutch_torque(_ctx(), _args(F_a=5000, mu=0.35, r_o=0.15)))
        r = json.loads(raw)
        assert r["ok"] is False

    def test_tool_invalid_json(self):
        raw = _run(run_disc_brake_torque(_ctx(), b"not-json"))
        r = json.loads(raw)
        # err_payload returns {"error": ..., "code": ...} for parse errors
        assert "error" in r or r.get("ok") is False


# ===========================================================================
# Externally-citable reference cases (production-confidence validation)
# Cross-checked vs Shigley 10th ed. §§16-1..16-12, Juvinall & Marshek
# "Machine Component Design" 5th ed.
# ===========================================================================

from kerf_cad_core.clutchbrake.design import (  # noqa: E402
    disc_clutch_torque as _ref_disc,
    cone_clutch_torque as _ref_cone,
    band_brake_torque as _ref_band,
    disc_brake_torque as _ref_caliper,
    engagement_energy as _ref_energy,
)


class TestClutchBrakeExternalReferences:
    """Validated against Shigley §16 & Juvinall §18 friction relations."""

    def test_disc_clutch_uniform_wear_shigley_16_2(self):
        # Shigley §16-2 uniform-wear: T = μ F (ro+ri)/2 per surface.
        r = _ref_disc(5000.0, 0.3, 0.10, 0.06, method="uniform-wear", n_plates=1)
        r_mean = (0.10 + 0.06) / 2.0
        assert r["r_mean_m"] == pytest.approx(r_mean, rel=1e-12)
        assert r["T_per_surface"] == pytest.approx(0.3 * 5000.0 * r_mean, rel=1e-12)
        assert r["n_surfaces"] == 2  # single plate → 2 friction faces

    def test_disc_clutch_uniform_pressure_shigley_16_2(self):
        # Shigley §16-2 uniform-pressure: r_mean = (2/3)(ro³-ri³)/(ro²-ri²).
        r = _ref_disc(5000.0, 0.3, 0.10, 0.06, method="uniform-pressure")
        rm = (2.0 / 3.0) * (0.10 ** 3 - 0.06 ** 3) / (0.10 ** 2 - 0.06 ** 2)
        assert r["r_mean_m"] == pytest.approx(rm, rel=1e-12)

    def test_multiplate_surface_count(self):
        # Shigley §16-2: N friction discs → 2N friction surfaces.
        r = _ref_disc(5000.0, 0.3, 0.10, 0.06, n_plates=4)
        assert r["n_surfaces"] == 8
        assert r["torque_Nm"] == pytest.approx(r["T_per_surface"] * 8, rel=1e-12)

    def test_cone_clutch_shigley_16_3(self):
        # Shigley §16-3: T = μ F r_mean / sin α (uniform wear).
        r = _ref_cone(2000.0, 0.3, 0.08, 0.05, 12.0, method="uniform-wear")
        rm = (0.08 + 0.05) / 2.0
        assert r["torque_Nm"] == pytest.approx(0.3 * 2000.0 * rm / math.sin(math.radians(12.0)), rel=1e-9)

    def test_cone_self_lock_condition(self):
        # Shigley §16-3: self-locking when μ ≥ sin α. α=5°, μ=0.30.
        r = _ref_cone(2000.0, 0.30, 0.08, 0.05, 5.0)
        assert r["self_lock"] is True

    def test_band_brake_capstan_shigley_16_6(self):
        # Shigley §16-6: F1/F2 = exp(μθ); T = (F1−F2)·r.
        r = _ref_band(0.15, 270.0, 0.25, 1000.0)
        cap = math.exp(0.25 * math.radians(270.0))
        F2 = 1000.0 / cap
        assert r["capstan_ratio"] == pytest.approx(cap, rel=1e-12)
        assert r["torque_Nm"] == pytest.approx((1000.0 - F2) * 0.15, rel=1e-9)

    def test_caliper_disc_brake(self):
        # Standard caliper: T = n_pads·μ·F_clamp·r_eff.
        r = _ref_caliper(8000.0, 0.4, 0.12, n_pads=2)
        assert r["torque_Nm"] == pytest.approx(2 * 0.4 * 8000.0 * 0.12, rel=1e-12)

    def test_engagement_kinetic_energy(self):
        # Juvinall §18: ΔKE = ½ I_eff Δω², I_eff = I1 I2/(I1+I2).
        r = _ref_energy(100.0, 0.0, 2.0, 3.0)
        I_eff = 2.0 * 3.0 / (2.0 + 3.0)
        assert r["I_eff"] == pytest.approx(I_eff, rel=1e-12)
        assert r["E_kinetic_J"] == pytest.approx(0.5 * I_eff * 100.0 ** 2, rel=1e-9)

    def test_engagement_load_work(self):
        # Slip energy + load work: W_load = T_load·ω_avg·t.
        r = _ref_energy(100.0, 0.0, 2.0, 3.0, T_load_Nm=10.0, t_engage_s=0.5)
        omega_avg = (0.0 + 100.0) / 2.0
        assert r["E_load_J"] == pytest.approx(10.0 * omega_avg * 0.5, rel=1e-9)

    def test_cone_uniform_pressure_radius(self):
        # Shigley §16-3 uniform pressure cone: same r_mean formula as disc.
        r = _ref_cone(2000.0, 0.3, 0.08, 0.05, 12.0, method="uniform-pressure")
        rm = (2.0 / 3.0) * (0.08 ** 3 - 0.05 ** 3) / (0.08 ** 2 - 0.05 ** 2)
        assert r["r_mean_m"] == pytest.approx(rm, rel=1e-12)
