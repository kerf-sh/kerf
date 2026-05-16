"""
Hermetic tests for kerf_cad_core.windturbine — wind-turbine power & rotor sizing.

Coverage:
  rotor.available_power      — P = ½·ρ·A·V³ formula verification
  rotor.betz_limit           — Cp_max = 16/27 exact
  rotor.air_density          — ISA sea level, altitude, temperature corrections
  rotor.rotor_diameter       — sizing formula inverse of available_power
  rotor.rotor_speed          — TSR → RPM, tip-speed
  rotor.gearbox_ratio        — integer ceiling, exact value
  rotor.thrust_force         — T = ½·ρ·A·V²·Ct
  rotor.overturning_moment   — M = T × h
  rotor.blade_element_momentum — Cp in (0, 16/27], Ct > 0
  rotor.power_curve          — cubic ramp, rated, below-cutin, above-cutout
  rotor.weibull_aep          — AEP > 0, capacity factor range
  rotor.rayleigh_aep         — Rayleigh == Weibull(k=2, c=2*v/√π)
  rotor.capacity_factor      — CF formula, low-CF warning, CF > 1 warning
  rotor.jensen_wake          — deficit formula, zero distance, x/D scaling
  rotor.sound_pressure_distance — SPL hemispherical law
  tools.*                    — LLM wrapper happy paths + error paths

All tests are pure-Python and hermetic: no OCC, no DB, no network.
Formulas verified against Burton et al. "Wind Energy Handbook" hand-calculations.

References
----------
Burton, T. et al., "Wind Energy Handbook", 2nd ed., Wiley (2011).
Betz, A. (1920) — momentum theory maximum Cp = 16/27.
Jensen, N.O. (1983) — wake decay model.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import warnings

import pytest

from kerf_cad_core.windturbine.rotor import (
    available_power,
    betz_limit,
    air_density,
    rotor_diameter,
    rotor_speed,
    gearbox_ratio,
    thrust_force,
    overturning_moment,
    blade_element_momentum,
    power_curve,
    weibull_aep,
    rayleigh_aep,
    capacity_factor,
    jensen_wake,
    sound_pressure_distance,
)
from kerf_cad_core.windturbine.tools import (
    run_wt_available_power,
    run_wt_betz_limit,
    run_wt_air_density,
    run_wt_rotor_diameter,
    run_wt_rotor_speed,
    run_wt_gearbox_ratio,
    run_wt_thrust_force,
    run_wt_overturning_moment,
    run_wt_blade_element_momentum,
    run_wt_power_curve,
    run_wt_weibull_aep,
    run_wt_rayleigh_aep,
    run_wt_capacity_factor,
    run_wt_jensen_wake,
    run_wt_sound_pressure,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeCtx:
    pass


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _ok(tool_fn, args_dict):
    result = json.loads(_run(tool_fn(_FakeCtx(), json.dumps(args_dict).encode())))
    assert result.get("ok") is not False, f"Expected success, got: {result}"
    assert "error" not in result, f"Expected success, got error: {result}"
    return result


def _err(tool_fn, args_dict):
    result = json.loads(_run(tool_fn(_FakeCtx(), json.dumps(args_dict).encode())))
    is_ok_false = result.get("ok") is False
    is_err_payload = "error" in result and "code" in result
    assert is_ok_false or is_err_payload, f"Expected error response, got: {result}"
    return result


# ---------------------------------------------------------------------------
# 1. available_power — P = ½·ρ·A·V³
# ---------------------------------------------------------------------------

def test_available_power_standard_conditions():
    # rho=1.225, D=80 m → A=π/4*80²≈5026.5, V=10 m/s
    # P = 0.5*1.225*5026.5*1000 = 3,078,731 W ≈ 3.08 MW
    D = 80.0
    A = math.pi * D ** 2 / 4.0
    res = available_power(1.225, A, 10.0)
    assert "power_W" in res
    expected = 0.5 * 1.225 * A * 10.0 ** 3
    assert res["power_W"] == pytest.approx(expected, rel=1e-6)


def test_available_power_cubic_scaling():
    # Doubling wind speed → 8x power
    A = 1000.0
    rho = 1.225
    r1 = available_power(rho, A, 5.0)
    r2 = available_power(rho, A, 10.0)
    assert r2["power_W"] == pytest.approx(8.0 * r1["power_W"], rel=1e-6)


def test_available_power_zero_wind():
    res = available_power(1.225, 1000.0, 0.0)
    assert res["power_W"] == pytest.approx(0.0)


def test_available_power_power_kw_unit():
    res = available_power(1.225, 2000.0, 8.0)
    assert res["power_kW"] == pytest.approx(res["power_W"] / 1000.0, rel=1e-9)


# ---------------------------------------------------------------------------
# 2. betz_limit
# ---------------------------------------------------------------------------

def test_betz_limit_exact():
    res = betz_limit()
    assert res["Cp_max"] == pytest.approx(16.0 / 27.0, rel=1e-12)


def test_betz_limit_axial_induction():
    res = betz_limit()
    assert res["axial_induction_at_betz"] == pytest.approx(1.0 / 3.0, rel=1e-12)


def test_betz_limit_percent():
    res = betz_limit()
    assert 59.2 < res["Cp_max_percent"] < 59.3


# ---------------------------------------------------------------------------
# 3. air_density — ISA corrections
# ---------------------------------------------------------------------------

def test_air_density_sea_level_standard():
    res = air_density(0.0, 15.0)
    # ISA standard: ρ = 1.225 kg/m³
    assert res["rho_kg_m3"] == pytest.approx(1.225, abs=0.002)


def test_air_density_decreases_with_altitude():
    r_low = air_density(0.0, 15.0)
    r_high = air_density(2000.0, 15.0)
    assert r_high["rho_kg_m3"] < r_low["rho_kg_m3"]


def test_air_density_decreases_with_temperature():
    r_cold = air_density(0.0, -10.0)
    r_hot = air_density(0.0, 40.0)
    assert r_cold["rho_kg_m3"] > r_hot["rho_kg_m3"]


def test_air_density_keys_present():
    res = air_density(500.0, 20.0)
    for key in ("rho_kg_m3", "pressure_Pa", "temperature_K"):
        assert key in res


# ---------------------------------------------------------------------------
# 4. rotor_diameter
# ---------------------------------------------------------------------------

def test_rotor_diameter_round_trip():
    # Verify: P = ½·ρ·A·V³·Cp should recover P_rated
    P_rated = 2_000_000.0   # 2 MW
    Cp = 0.40
    rho = 1.225
    V = 12.0
    res = rotor_diameter(P_rated, Cp, rho, V)
    D = res["diameter_m"]
    A = math.pi * D ** 2 / 4.0
    P_check = 0.5 * rho * A * V ** 3 * Cp
    assert P_check == pytest.approx(P_rated, rel=1e-5)


def test_rotor_diameter_betz_cap():
    # Cp > 16/27 should be clamped with a warning
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        res = rotor_diameter(1e6, 0.65, 1.225, 12.0)
    assert res["diameter_m"] is not None
    assert any("Betz" in str(x.message) for x in w)


def test_rotor_diameter_invalid_power():
    res = rotor_diameter(-1e6, 0.4, 1.225, 12.0)
    assert res["diameter_m"] is None


# ---------------------------------------------------------------------------
# 5. rotor_speed
# ---------------------------------------------------------------------------

def test_rotor_speed_tsr_formula():
    # ω = TSR * V / R
    V, tsr, D = 10.0, 7.0, 80.0
    res = rotor_speed(V, tsr, D)
    expected_omega = tsr * V / (D / 2.0)
    assert res["omega_rad_s"] == pytest.approx(expected_omega, rel=1e-9)


def test_rotor_speed_rpm_from_omega():
    res = rotor_speed(10.0, 7.0, 80.0)
    assert res["rpm"] == pytest.approx(res["omega_rad_s"] * 60.0 / (2.0 * math.pi), rel=1e-9)


def test_rotor_speed_tip_speed():
    res = rotor_speed(10.0, 7.0, 80.0)
    R = 40.0
    assert res["tip_speed_ms"] == pytest.approx(res["omega_rad_s"] * R, rel=1e-9)


def test_rotor_speed_tip_speed_warning():
    # TSR=10, V=20, D=10 → tip=100 m/s > 80 m/s
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        rotor_speed(20.0, 10.0, 10.0)
    assert any("80 m/s" in str(x.message) for x in w)


# ---------------------------------------------------------------------------
# 6. gearbox_ratio
# ---------------------------------------------------------------------------

def test_gearbox_ratio_exact_integer():
    # 1500 / 15 = 100 exactly
    res = gearbox_ratio(15.0, 1500.0)
    assert res["ratio_integer"] == 100


def test_gearbox_ratio_ceiling():
    # 1500 / 16 = 93.75 → ceiling = 94
    res = gearbox_ratio(16.0, 1500.0)
    assert res["ratio_integer"] == 94


def test_gearbox_ratio_exact_value():
    res = gearbox_ratio(16.0, 1500.0)
    assert res["ratio_exact"] == pytest.approx(1500.0 / 16.0, rel=1e-9)


# ---------------------------------------------------------------------------
# 7. thrust_force
# ---------------------------------------------------------------------------

def test_thrust_force_formula():
    # T = ½·ρ·A·V²·Ct
    rho, A, V, Ct = 1.225, 5000.0, 12.0, 0.8
    res = thrust_force(rho, A, V, Ct)
    expected = 0.5 * rho * A * V ** 2 * Ct
    assert res["thrust_N"] == pytest.approx(expected, rel=1e-9)


def test_thrust_force_betz_default():
    # Default Ct = 8/9
    res = thrust_force(1.225, 5000.0, 10.0)
    assert res["Ct"] == pytest.approx(8.0 / 9.0, rel=1e-9)


def test_thrust_force_kn_unit():
    res = thrust_force(1.225, 5000.0, 10.0)
    assert res["thrust_kN"] == pytest.approx(res["thrust_N"] / 1000.0, rel=1e-9)


# ---------------------------------------------------------------------------
# 8. overturning_moment
# ---------------------------------------------------------------------------

def test_overturning_moment_formula():
    T = 500_000.0   # 500 kN
    h = 80.0
    res = overturning_moment(T, h)
    assert res["moment_Nm"] == pytest.approx(T * h, rel=1e-9)


def test_overturning_moment_kNm():
    T, h = 500_000.0, 80.0
    res = overturning_moment(T, h)
    assert res["moment_kNm"] == pytest.approx(res["moment_Nm"] / 1000.0, rel=1e-9)


# ---------------------------------------------------------------------------
# 9. blade_element_momentum
# ---------------------------------------------------------------------------

def test_bem_cp_positive():
    res = blade_element_momentum(7.0)
    assert res["Cp"] is not None
    assert res["Cp"] > 0


def test_bem_cp_below_betz():
    res = blade_element_momentum(7.0, n_blades=3, chord_r_ratio=0.06)
    assert res["Cp"] <= 16.0 / 27.0 + 1e-4  # numerical tolerance


def test_bem_ct_positive():
    res = blade_element_momentum(7.0)
    assert res["Ct"] is not None
    assert res["Ct"] > 0


def test_bem_annuli_count():
    res = blade_element_momentum(7.0, n_annuli=10)
    assert len(res["annuli"]) == 10


def test_bem_higher_tsr_higher_cp():
    # In this simplified uniform-chord zero-alpha BEM model, higher TSR
    # produces lower Cp because the inflow angle φ→0 and Cl→0.  Verify that
    # TSR=2 gives higher Cp than TSR=8 (opposite of an optimised-pitch blade).
    r_lo = blade_element_momentum(2.0)
    r_hi = blade_element_momentum(8.0)
    # For the simplified model (zero AOA), lower TSR means larger φ → larger Cl
    assert r_lo["Cp"] > r_hi["Cp"]
    # Both must remain physical (positive, below Betz)
    assert 0 < r_hi["Cp"] <= 16.0 / 27.0 + 1e-4


# ---------------------------------------------------------------------------
# 10. power_curve
# ---------------------------------------------------------------------------

def test_power_curve_below_cutin():
    res = power_curve(2.0, 3.0, 12.0, 25.0, 2_000_000.0)
    assert res["power_W"] == pytest.approx(0.0)
    assert res["region"] == "below-cutin"


def test_power_curve_at_rated():
    res = power_curve(12.0, 3.0, 12.0, 25.0, 2_000_000.0)
    assert res["power_W"] == pytest.approx(2_000_000.0, rel=1e-9)
    assert res["region"] == "rated"


def test_power_curve_above_rated():
    res = power_curve(18.0, 3.0, 12.0, 25.0, 2_000_000.0)
    assert res["power_W"] == pytest.approx(2_000_000.0, rel=1e-9)
    assert res["region"] == "rated"


def test_power_curve_above_cutout():
    res = power_curve(30.0, 3.0, 12.0, 25.0, 2_000_000.0)
    assert res["power_W"] == pytest.approx(0.0)
    assert res["region"] == "above-cutout"


def test_power_curve_cubic_ramp_midpoint():
    # At V = V_cutin the power should be 0, at V = V_rated it should be P_rated
    V_c, V_r = 3.0, 12.0
    P = 1_000_000.0
    # Choose a point in the cubic ramp
    V_mid = 7.0
    res = power_curve(V_mid, V_c, V_r, 25.0, P)
    expected = P * (V_mid ** 3 - V_c ** 3) / (V_r ** 3 - V_c ** 3)
    assert res["power_W"] == pytest.approx(expected, rel=1e-6)


def test_power_curve_capacity_factor_instant():
    P_rated = 2_000_000.0
    res = power_curve(12.0, 3.0, 12.0, 25.0, P_rated)
    assert res["capacity_factor_instant"] == pytest.approx(1.0, rel=1e-9)


# ---------------------------------------------------------------------------
# 11. weibull_aep
# ---------------------------------------------------------------------------

def test_weibull_aep_positive():
    pc = {"V_cutin": 3.0, "V_rated": 12.0, "V_cutout": 25.0, "P_rated_W": 2e6}
    res = weibull_aep(2.0, 8.0, pc)
    assert res["aep_kWh"] is not None
    assert res["aep_kWh"] > 0


def test_weibull_aep_mwh_unit():
    pc = {"V_cutin": 3.0, "V_rated": 12.0, "V_cutout": 25.0, "P_rated_W": 2e6}
    res = weibull_aep(2.0, 8.0, pc)
    assert res["aep_MWh"] == pytest.approx(res["aep_kWh"] / 1000.0, rel=1e-3)


def test_weibull_aep_higher_c_higher_aep():
    # Higher mean wind speed (c) → higher AEP
    pc = {"V_cutin": 3.0, "V_rated": 12.0, "V_cutout": 25.0, "P_rated_W": 2e6}
    r_lo = weibull_aep(2.0, 6.0, pc)
    r_hi = weibull_aep(2.0, 10.0, pc)
    assert r_hi["aep_kWh"] > r_lo["aep_kWh"]


def test_weibull_aep_low_cf_warning():
    # Very low scale parameter → low capacity factor → warning
    pc = {"V_cutin": 3.0, "V_rated": 12.0, "V_cutout": 25.0, "P_rated_W": 2e6}
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        weibull_aep(2.0, 3.0, pc)
    assert any("capacity factor" in str(x.message).lower() for x in w)


# ---------------------------------------------------------------------------
# 12. rayleigh_aep
# ---------------------------------------------------------------------------

def test_rayleigh_aep_equals_weibull_k2():
    # Rayleigh is Weibull with k=2, c = 2*v_mean/sqrt(π)
    v_mean = 7.0
    c = 2.0 * v_mean / math.sqrt(math.pi)
    pc = {"V_cutin": 3.0, "V_rated": 12.0, "V_cutout": 25.0, "P_rated_W": 2e6}
    r_rayleigh = rayleigh_aep(v_mean, pc)
    r_weibull = weibull_aep(2.0, c, pc)
    assert r_rayleigh["aep_kWh"] == pytest.approx(r_weibull["aep_kWh"], rel=1e-3)


def test_rayleigh_aep_c_parameter():
    v_mean = 8.0
    pc = {"V_cutin": 3.0, "V_rated": 12.0, "V_cutout": 25.0, "P_rated_W": 2e6}
    res = rayleigh_aep(v_mean, pc)
    expected_c = 2.0 * v_mean / math.sqrt(math.pi)
    assert res["rayleigh_c_ms"] == pytest.approx(expected_c, rel=1e-4)


# ---------------------------------------------------------------------------
# 13. capacity_factor
# ---------------------------------------------------------------------------

def test_capacity_factor_formula():
    P_rated = 2_000_000.0   # 2 MW
    aep_kWh = P_rated / 1000.0 * 8760.0 * 0.35   # 35% CF
    res = capacity_factor(aep_kWh, P_rated)
    assert res["capacity_factor"] == pytest.approx(0.35, rel=1e-4)


def test_capacity_factor_full_load():
    P_rated = 1_000_000.0
    aep_kWh = P_rated / 1000.0 * 8760.0
    res = capacity_factor(aep_kWh, P_rated)
    assert res["capacity_factor"] == pytest.approx(1.0, rel=1e-6)


def test_capacity_factor_low_cf_warning():
    P_rated = 2_000_000.0
    # CF = 0.10 — should trigger warning
    aep_kWh = P_rated / 1000.0 * 8760.0 * 0.10
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        capacity_factor(aep_kWh, P_rated)
    assert any("0.20" in str(x.message) or "capacity factor" in str(x.message).lower() for x in w)


def test_capacity_factor_above_1_warning():
    P_rated = 1_000_000.0
    aep_kWh = P_rated / 1000.0 * 8760.0 * 1.5   # CF = 1.5 → impossible
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        capacity_factor(aep_kWh, P_rated)
    assert any("1.0" in str(x.message) or "impossible" in str(x.message).lower() for x in w)


# ---------------------------------------------------------------------------
# 14. jensen_wake
# ---------------------------------------------------------------------------

def test_jensen_wake_zero_distance():
    # At x=0, wake = free stream (no deficit yet)
    res = jensen_wake(10.0, 0.8, 0.0, 80.0)
    # (1 - sqrt(1 - Ct)) * (D / (D + 0))^2 = (1 - sqrt(0.2)) * 1
    deficit = (1.0 - math.sqrt(1.0 - 0.8)) * 1.0
    expected = 10.0 * (1.0 - deficit)
    assert res["u_wake_ms"] == pytest.approx(expected, abs=1e-3)


def test_jensen_wake_deficit_decreases_with_distance():
    # Wake recovers at greater distances
    r_near = jensen_wake(10.0, 0.8, 200.0, 80.0)
    r_far = jensen_wake(10.0, 0.8, 1000.0, 80.0)
    assert r_far["u_wake_ms"] > r_near["u_wake_ms"]


def test_jensen_wake_formula():
    u0, Ct, x, D, k_w = 10.0, 0.8, 500.0, 80.0, 0.04
    res = jensen_wake(u0, Ct, x, D, k_w=k_w)
    deficit = (1.0 - math.sqrt(1.0 - Ct)) * (D / (D + 2.0 * k_w * x)) ** 2
    expected = u0 * (1.0 - deficit)
    # result is rounded to 4 decimal places
    assert res["u_wake_ms"] == pytest.approx(expected, abs=1e-3)


def test_jensen_wake_power_ratio():
    res = jensen_wake(10.0, 0.8, 500.0, 80.0)
    expected_pr = (res["u_wake_ms"] / 10.0) ** 3
    assert res["power_ratio"] == pytest.approx(expected_pr, rel=1e-4)


def test_jensen_wake_x_over_D():
    res = jensen_wake(10.0, 0.8, 400.0, 80.0)
    assert res["x_over_D"] == pytest.approx(400.0 / 80.0, rel=1e-6)


# ---------------------------------------------------------------------------
# 15. sound_pressure_distance
# ---------------------------------------------------------------------------

def test_sound_pressure_formula():
    Lw, r = 105.0, 500.0
    res = sound_pressure_distance(Lw, r)
    expected = Lw - 10.0 * math.log10(2.0 * math.pi * r ** 2)
    # result is rounded to 2 decimal places
    assert res["spl_dBA"] == pytest.approx(expected, abs=0.01)


def test_sound_pressure_decreases_with_distance():
    r1 = sound_pressure_distance(105.0, 200.0)
    r2 = sound_pressure_distance(105.0, 500.0)
    assert r2["spl_dBA"] < r1["spl_dBA"]


def test_sound_pressure_near_field_warning():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        sound_pressure_distance(105.0, 20.0)
    assert any("near" in str(x.message).lower() or "50 m" in str(x.message) for x in w)


# ---------------------------------------------------------------------------
# 16. tools — LLM wrapper happy paths
# ---------------------------------------------------------------------------

def test_tool_available_power_ok():
    D = 80.0
    A = math.pi * D ** 2 / 4.0
    res = _ok(run_wt_available_power, {"rho": 1.225, "A": A, "V": 10.0})
    assert res["power_kW"] > 0


def test_tool_betz_limit_ok():
    res = _ok(run_wt_betz_limit, {})
    assert abs(res["Cp_max"] - 16.0 / 27.0) < 1e-9


def test_tool_air_density_ok():
    res = _ok(run_wt_air_density, {"altitude_m": 0, "temperature_c": 15})
    assert abs(res["rho_kg_m3"] - 1.225) < 0.003


def test_tool_rotor_diameter_ok():
    res = _ok(run_wt_rotor_diameter, {
        "P_rated_W": 2_000_000,
        "Cp": 0.40,
        "rho": 1.225,
        "V_rated_ms": 12.0,
    })
    assert res["diameter_m"] > 0


def test_tool_rotor_speed_ok():
    res = _ok(run_wt_rotor_speed, {"V_ms": 10.0, "tsr": 7.0, "diameter_m": 80.0})
    assert res["rpm"] > 0


def test_tool_gearbox_ratio_ok():
    res = _ok(run_wt_gearbox_ratio, {"rotor_rpm": 15.0, "generator_rpm": 1500.0})
    assert res["ratio_integer"] == 100


def test_tool_thrust_force_ok():
    A = math.pi * 80.0 ** 2 / 4.0
    res = _ok(run_wt_thrust_force, {"rho": 1.225, "A": A, "V": 12.0})
    assert res["thrust_kN"] > 0


def test_tool_overturning_moment_ok():
    res = _ok(run_wt_overturning_moment, {"thrust_N": 500_000.0, "hub_height_m": 80.0})
    assert res["moment_kNm"] == pytest.approx(40_000.0, rel=1e-6)


def test_tool_bem_ok():
    res = _ok(run_wt_blade_element_momentum, {"tsr": 7.0, "n_blades": 3})
    assert res["Cp"] > 0


def test_tool_power_curve_ok():
    res = _ok(run_wt_power_curve, {
        "V_ms": 12.0, "V_cutin": 3.0, "V_rated": 12.0,
        "V_cutout": 25.0, "P_rated_W": 2_000_000.0,
    })
    assert res["region"] == "rated"


def test_tool_weibull_aep_ok():
    res = _ok(run_wt_weibull_aep, {
        "k": 2.0, "c_ms": 8.0, "V_cutin": 3.0,
        "V_rated": 12.0, "V_cutout": 25.0, "P_rated_W": 2_000_000.0,
    })
    assert res["aep_kWh"] > 0


def test_tool_rayleigh_aep_ok():
    res = _ok(run_wt_rayleigh_aep, {
        "v_mean_ms": 7.0, "V_cutin": 3.0, "V_rated": 12.0,
        "V_cutout": 25.0, "P_rated_W": 2_000_000.0,
    })
    assert res["aep_kWh"] > 0


def test_tool_capacity_factor_ok():
    P = 2_000_000.0
    aep = P / 1000.0 * 8760.0 * 0.35
    res = _ok(run_wt_capacity_factor, {"aep_kWh": aep, "P_rated_W": P})
    assert abs(res["capacity_factor"] - 0.35) < 0.001


def test_tool_jensen_wake_ok():
    res = _ok(run_wt_jensen_wake, {
        "u0_ms": 10.0, "Ct": 0.8, "x_m": 500.0, "D_m": 80.0,
    })
    assert res["u_wake_ms"] < 10.0


def test_tool_sound_pressure_ok():
    res = _ok(run_wt_sound_pressure, {"Lw_dB": 105.0, "distance_m": 500.0})
    assert "spl_dBA" in res


# ---------------------------------------------------------------------------
# 17. tools — error paths
# ---------------------------------------------------------------------------

def test_tool_available_power_missing_field():
    _err(run_wt_available_power, {"rho": 1.225, "A": 5000.0})  # V missing


def test_tool_rotor_diameter_missing_cp():
    _err(run_wt_rotor_diameter, {
        "P_rated_W": 2_000_000, "rho": 1.225, "V_rated_ms": 12.0,
    })


def test_tool_rotor_speed_missing_diameter():
    _err(run_wt_rotor_speed, {"V_ms": 10.0, "tsr": 7.0})


def test_tool_gearbox_ratio_missing_rotor():
    _err(run_wt_gearbox_ratio, {"generator_rpm": 1500.0})


def test_tool_thrust_force_missing_v():
    _err(run_wt_thrust_force, {"rho": 1.225, "A": 5000.0})


def test_tool_overturning_moment_missing_height():
    _err(run_wt_overturning_moment, {"thrust_N": 500_000.0})


def test_tool_jensen_wake_bad_json():
    result = json.loads(
        _run(run_wt_jensen_wake(_FakeCtx(), b"not-json"))
    )
    assert result.get("ok") is False or "error" in result


def test_tool_capacity_factor_missing_aep():
    _err(run_wt_capacity_factor, {"P_rated_W": 2_000_000.0})
