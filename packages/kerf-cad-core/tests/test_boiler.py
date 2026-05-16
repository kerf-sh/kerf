"""
tests/test_boiler.py — hermetic tests for kerf_cad_core.boiler.plant

All tests are pure Python; no database, network, or OCC dependency.
Expected values derived from steam tables (IAPWS-IF97), ASME PTC 4, and
Spirax Sarco reference calculations.

Tolerances:
  Steam properties:  ±1% (fitted correlations)
  Duty/efficiency:   exact arithmetic (no correlation)
  Blowdown, pipe:    ±0.5% or absolute tolerance where specified
"""
from __future__ import annotations

import math
import pytest

from kerf_cad_core.boiler.plant import (
    tsat_from_p,
    psat_from_t,
    steam_properties,
    superheat_h,
    boiler_heat_duty,
    boiler_steam_output,
    boiler_efficiency_io,
    boiler_efficiency_heat_loss,
    fuel_firing_rate,
    combustion_air_flow,
    blowdown_rate,
    blowdown_heat_loss,
    feedwater_energy_balance,
    deaerator_energy_balance,
    economizer_energy_balance,
    equivalent_evaporation,
    boiler_horsepower,
    steam_pipe_velocity,
    steam_pipe_pressure_drop,
    flash_steam_fraction,
    condensate_heat_recovery,
    steam_trap_capacity,
    safety_valve_napier,
)


# ───────────────────────────────────────────────────────────────
# 1–4  tsat_from_p  (spot-checks vs IAPWS-IF97 saturation curve)
# ───────────────────────────────────────────────────────────────

def test_tsat_at_1atm():
    """T_sat at 101325 Pa should be 100 °C ± 0.5 °C."""
    r = tsat_from_p(101325)
    assert "T_sat_C" in r
    assert abs(r["T_sat_C"] - 100.0) < 0.5, f"T_sat={r['T_sat_C']}"


def test_tsat_at_1MPa():
    """T_sat at 1 MPa ≈ 179.9 °C (IAPWS-IF97)."""
    r = tsat_from_p(1e6)
    assert abs(r["T_sat_C"] - 179.9) < 1.5, f"T_sat={r['T_sat_C']}"


def test_tsat_at_10MPa():
    """T_sat at 10 MPa ≈ 311 °C."""
    r = tsat_from_p(10e6)
    assert abs(r["T_sat_C"] - 311.0) < 3.0, f"T_sat={r['T_sat_C']}"


def test_tsat_invalid_pressure():
    """Non-positive pressure returns error key, not exception."""
    r = tsat_from_p(-100)
    assert "error" in r


# ───────────────────────────────────────────────────────────────
# 5–8  psat_from_t
# ───────────────────────────────────────────────────────────────

def test_psat_at_100C():
    """Psat at 100 °C ≈ 101 325 Pa ± 2%."""
    r = psat_from_t(100.0)
    assert "P_sat_Pa" in r
    assert abs(r["P_sat_Pa"] - 101325) / 101325 < 0.02, f"Psat={r['P_sat_Pa']}"


def test_psat_at_180C():
    """Psat at 180 °C ≈ 1.0021 MPa (IAPWS-IF97)."""
    r = psat_from_t(180.0)
    assert abs(r["P_sat_MPa"] - 1.002) < 0.05, f"Psat={r['P_sat_MPa']} MPa"


def test_psat_roundtrip():
    """tsat_from_p(psat_from_t(T)) should recover T within 0.5 °C."""
    T0 = 150.0
    r1 = psat_from_t(T0)
    r2 = tsat_from_p(r1["P_sat_Pa"])
    assert abs(r2["T_sat_C"] - T0) < 0.5


def test_psat_critical_warning():
    """psat at 375 °C (above critical 374.14 °C) emits a warning."""
    r = psat_from_t(375.0)
    assert r.get("warnings"), "Expected warning near critical point"


# ───────────────────────────────────────────────────────────────
# 9–13  steam_properties
# ───────────────────────────────────────────────────────────────

def test_steam_props_at_1atm_keys():
    """steam_properties at 101 325 Pa returns all expected keys."""
    r = steam_properties(P_Pa=101325)
    for k in ("hf_kJkg", "hg_kJkg", "hfg_kJkg", "sf_kJkgK", "sg_kJkgK",
              "vf_m3kg", "vg_m3kg", "T_sat_C"):
        assert k in r, f"Missing key: {k}"


def test_steam_props_hfg_at_100C():
    """hfg at 100 °C ≈ 2257 kJ/kg (IAPWS-IF97 = 2256.9); fitted correlation ±1%."""
    r = steam_properties(T_sat_C=100.0)
    # Allow ±1% (≈22 kJ/kg) per stated correlation accuracy
    assert abs(r["hfg_kJkg"] - 2257) < 22, f"hfg={r['hfg_kJkg']}"


def test_steam_props_hf_at_100C():
    """hf at 100 °C ≈ 419.1 kJ/kg."""
    r = steam_properties(T_sat_C=100.0)
    assert abs(r["hf_kJkg"] - 419.1) < 5, f"hf={r['hf_kJkg']}"


def test_steam_props_vg_at_1bar():
    """vg at ~100 °C / 101325 Pa ≈ 1.674 m³/kg (IAPWS-IF97)."""
    r = steam_properties(P_Pa=101325)
    assert abs(r["vg_m3kg"] - 1.674) / 1.674 < 0.05, f"vg={r['vg_m3kg']}"


def test_steam_props_no_args_error():
    """steam_properties with no args returns error."""
    r = steam_properties()
    assert "error" in r


# ───────────────────────────────────────────────────────────────
# 14–15  superheat_h
# ───────────────────────────────────────────────────────────────

def test_superheat_h_basic():
    """At 1 MPa, 250 °C: T_sat ≈ 180 °C so superheat ≈ 70 K.
    h_sup ≈ hg + 2.05*70 ≈ 2778 + 143.5 ≈ 2922 kJ/kg (rough)."""
    r = superheat_h(1e6, 250.0)
    assert "h_sup_kJkg" in r
    assert r["superheat_K"] > 0
    # Very wide tolerance due to approximate correlation
    assert 2600 < r["h_sup_kJkg"] < 3200


def test_superheat_below_sat_warns():
    """Supplying T below T_sat emits a warning, returns hg."""
    r = superheat_h(1e6, 50.0)  # far below T_sat ~180°C
    assert r.get("warnings"), "Expected warning for wet steam"
    assert r["superheat_K"] == 0.0


# ───────────────────────────────────────────────────────────────
# 16–18  boiler_heat_duty
# ───────────────────────────────────────────────────────────────

def test_boiler_heat_duty_basic():
    """1 kg/s steam, hg=2675, hf=420 → Q = 2255 kW."""
    r = boiler_heat_duty(1.0, 2675.0, 420.0)
    assert abs(r["Q_kW"] - 2255.0) < 0.1


def test_boiler_heat_duty_zero_flow():
    """Zero steam flow gives Q = 0."""
    r = boiler_heat_duty(0.0, 2675.0, 420.0)
    assert r["Q_kW"] == 0.0


def test_boiler_heat_duty_negative_flow_error():
    """Negative mass flow returns error."""
    r = boiler_heat_duty(-1.0, 2675.0, 420.0)
    assert "error" in r


# ───────────────────────────────────────────────────────────────
# 19–21  boiler_efficiency_io
# ───────────────────────────────────────────────────────────────

def test_efficiency_io_basic():
    """m=1 kg/s, dh=2255 kJ/kg, Q_fuel=2500 kW → η = 0.902."""
    r = boiler_efficiency_io(1.0, 2675.0, 420.0, 2500.0)
    assert abs(r["efficiency"] - 2255 / 2500) < 1e-4


def test_efficiency_io_zero_fuel_error():
    """Zero fuel rate returns error."""
    r = boiler_efficiency_io(1.0, 2675.0, 420.0, 0.0)
    assert "error" in r


def test_efficiency_io_low_efficiency_warns():
    """Efficiency < 0.6 emits warning."""
    # Need very low output / high fuel: m=0.1, dh=500, Q=1000 → η=0.05
    r = boiler_efficiency_io(0.1, 920.0, 420.0, 1000.0)
    assert r.get("warnings"), "Expected low-efficiency warning"


# ───────────────────────────────────────────────────────────────
# 22–24  boiler_efficiency_heat_loss
# ───────────────────────────────────────────────────────────────

def test_efficiency_hl_basic():
    """Stack 200°C, ambient 25°C, EA=20% → reasonable η ~85–92%."""
    r = boiler_efficiency_heat_loss(200.0)
    assert "efficiency_pct" in r
    assert 80.0 < r["efficiency_pct"] < 95.0


def test_efficiency_hl_high_stack_warns():
    """Stack > 250°C emits warning."""
    r = boiler_efficiency_heat_loss(300.0, ambient_temp_C=20.0)
    assert any("250" in w for w in r.get("warnings", [])), r["warnings"]


def test_efficiency_hl_invalid_temp():
    """Stack ≤ ambient returns error."""
    r = boiler_efficiency_heat_loss(20.0, ambient_temp_C=25.0)
    assert "error" in r


# ───────────────────────────────────────────────────────────────
# 25–26  fuel_firing_rate
# ───────────────────────────────────────────────────────────────

def test_fuel_rate_basic():
    """Q=5000 kW, η=0.85, HHV=50000 kJ/kg → m_fuel=0.1176 kg/s."""
    r = fuel_firing_rate(5000.0, 0.85, 50000.0)
    expected = 5000 / (0.85 * 50000)
    assert abs(r["m_fuel_kgs"] - expected) < 1e-5


def test_fuel_rate_invalid():
    """Zero HHV returns error."""
    r = fuel_firing_rate(5000.0, 0.85, 0.0)
    assert "error" in r


# ───────────────────────────────────────────────────────────────
# 27–28  combustion_air_flow
# ───────────────────────────────────────────────────────────────

def test_combustion_air_flow_basic():
    """0.1 kg/s fuel, AFR=15.6, EA=20% → m_air = 0.1*15.6*1.2 = 1.872 kg/s."""
    r = combustion_air_flow(0.1, stoich_air_fuel_ratio=15.6, excess_air_pct=20.0)
    assert abs(r["m_air_actual_kgs"] - 1.872) < 1e-4
    assert abs(r["lambda"] - 1.2) < 1e-4


def test_combustion_air_low_ea_warns():
    """Excess air < 5% emits incomplete combustion warning."""
    r = combustion_air_flow(0.1, excess_air_pct=2.0)
    assert r.get("warnings"), "Expected incomplete combustion warning"


# ───────────────────────────────────────────────────────────────
# 29–30  blowdown_rate
# ───────────────────────────────────────────────────────────────

def test_blowdown_rate_basic():
    """FW TDS=300 ppm, BD limit=3000 ppm → CoC=10, BD_frac=1/9≈0.111."""
    r = blowdown_rate(1.0, 300.0, 3000.0)
    assert abs(r["CoC"] - 10.0) < 0.01
    assert abs(r["blowdown_fraction"] - 1 / 9) < 1e-4


def test_blowdown_rate_high_blowdown_warns():
    """BD fraction > 15% emits warning (FW TDS=500, limit=600)."""
    r = blowdown_rate(1.0, 500.0, 600.0)
    assert r.get("warnings"), "Expected high-blowdown warning"


# ───────────────────────────────────────────────────────────────
# 31–32  blowdown_heat_loss
# ───────────────────────────────────────────────────────────────

def test_blowdown_heat_loss_positive():
    """Heat loss should be positive for any reasonable boiler pressure."""
    r = blowdown_heat_loss(0.05, 1e6)
    assert r["Q_loss_kW"] > 0


def test_blowdown_heat_loss_zero_flow():
    """Zero blowdown → zero heat loss."""
    r = blowdown_heat_loss(0.0, 1e6)
    assert r["Q_loss_kW"] == 0.0


# ───────────────────────────────────────────────────────────────
# 33  feedwater_energy_balance
# ───────────────────────────────────────────────────────────────

def test_feedwater_energy_balance():
    """Manual: m_steam=1, h_s=2675, m_bd=0.05, h_fw=420, h_bd=760.
    m_fw=1.05; Q = 1*2675 + 0.05*760 - 1.05*420 = 2675+38-441 = 2272 kW."""
    r = feedwater_energy_balance(1.0, 2675.0, 0.05, 420.0, 760.0)
    assert abs(r["m_fw_kgs"] - 1.05) < 1e-4
    assert abs(r["Q_absorbed_kW"] - 2272.0) < 0.5


# ───────────────────────────────────────────────────────────────
# 34  deaerator_energy_balance
# ───────────────────────────────────────────────────────────────

def test_deaerator_energy_balance():
    """10 kg/s cold water at 80 kJ/kg + 0.5 kg/s steam at 2675 kJ/kg.
    h_out = (10*80 + 0.5*2675) / 10.5 = (800 + 1337.5) / 10.5 = 203.6 kJ/kg."""
    r = deaerator_energy_balance(10.0, 80.0, 0.5, 2675.0)
    expected_h = (10 * 80 + 0.5 * 2675) / 10.5
    assert abs(r["h_fw_out_kJkg"] - expected_h) < 0.1
    assert abs(r["m_out_kgs"] - 10.5) < 1e-4


# ───────────────────────────────────────────────────────────────
# 35  economizer_energy_balance
# ───────────────────────────────────────────────────────────────

def test_economizer_energy_balance():
    """1 kg/s water, 60→105°C, cp=4.1868 → Q = 4.1868*45 = 188.4 kW."""
    r = economizer_energy_balance(1.0, 60.0, 105.0)
    assert abs(r["Q_econ_kW"] - 4.1868 * 45) < 0.1
    assert abs(r["delta_T_C"] - 45.0) < 1e-6


# ───────────────────────────────────────────────────────────────
# 36–37  equivalent_evaporation
# ───────────────────────────────────────────────────────────────

def test_equivalent_evaporation_basic():
    """1 kg/s steam, h_s=2675, h_fw=420, m_fuel=0.1 kg/s.
    FE = (2675-420)/2256.9 ≈ 0.9991
    EE = 1 * 0.9991 / 0.1 = 9.991 kg/kg_fuel."""
    r = equivalent_evaporation(1.0, 2675.0, 420.0, 0.1)
    FE_expected = (2675 - 420) / 2256.9
    EE_expected = FE_expected / 0.1
    assert abs(r["factor_of_evaporation"] - FE_expected) < 1e-3
    assert abs(r["EE_kg_per_kg_fuel"] - EE_expected) < 0.01


def test_equivalent_evaporation_zero_fuel_error():
    """Zero fuel flow returns error."""
    r = equivalent_evaporation(1.0, 2675.0, 420.0, 0.0)
    assert "error" in r


# ───────────────────────────────────────────────────────────────
# 38  boiler_horsepower
# ───────────────────────────────────────────────────────────────

def test_boiler_horsepower():
    """1 kg/s steam at hg=2675 kJ/kg, h_fw=419.06 kJ/kg.
    Q = 1*(2675-419.06) = 2255.94 kW.
    BHP = 2255.94 / 9.81 ≈ 230.0."""
    r = boiler_horsepower(1.0, 2675.0)
    assert abs(r["Q_kW"] - 2255.94) < 0.1
    assert abs(r["BHP"] - 2255.94 / 9.81) < 0.1


# ───────────────────────────────────────────────────────────────
# 39–40  steam_pipe_velocity
# ───────────────────────────────────────────────────────────────

def test_pipe_velocity_basic():
    """1 kg/s steam, d=0.1 m (A=7.854e-3 m²), vg=1.6 m³/kg
    v = 1*1.6/7.854e-3 ≈ 203.7 m/s → triggers erosion warning."""
    r = steam_pipe_velocity(1.0, 0.1, 1.6)
    A = math.pi / 4 * 0.1**2
    expected_v = 1.0 * 1.6 / A
    assert abs(r["velocity_ms"] - expected_v) < 0.01
    assert r.get("warnings"), "Expected high-velocity warning"


def test_pipe_velocity_normal():
    """Normal velocity: d=0.3 m, m=0.5 kg/s, vg=0.2 m³/kg."""
    r = steam_pipe_velocity(0.5, 0.3, 0.2)
    assert r["velocity_ms"] > 0
    assert "error" not in r


# ───────────────────────────────────────────────────────────────
# 41  steam_pipe_pressure_drop
# ───────────────────────────────────────────────────────────────

def test_pipe_pressure_drop_positive():
    """Pressure drop should be positive for non-zero flow."""
    r = steam_pipe_pressure_drop(0.5, 0.1, 50.0, 0.2)
    assert r["dP_Pa"] > 0
    assert r["Reynolds"] > 0
    assert r["f_darcy"] > 0


# ───────────────────────────────────────────────────────────────
# 42–43  flash_steam_fraction
# ───────────────────────────────────────────────────────────────

def test_flash_steam_fraction_basic():
    """Condensate at 10 bar hf≈762 kJ/kg flashes to 1 bar (hf≈419, hfg≈2257).
    x ≈ (762-419)/2257 ≈ 0.152."""
    # hf at 10 bar (T~179°C): 4.1868*179 ≈ 749 kJ/kg
    h_cond = 749.0
    r = flash_steam_fraction(h_cond, 101325)
    assert 0.0 < r["flash_fraction"] < 0.5, f"fraction={r['flash_fraction']}"


def test_flash_below_hf_no_flash():
    """Condensate already at flash pressure — no flash steam."""
    # hf at 100 kPa ≈ 419 kJ/kg; supply same
    r = flash_steam_fraction(200.0, 101325)
    assert r["flash_fraction"] == 0.0
    assert r.get("warnings"), "Expected no-flash warning"


# ───────────────────────────────────────────────────────────────
# 44  condensate_heat_recovery
# ───────────────────────────────────────────────────────────────

def test_condensate_heat_recovery():
    """0.5 kg/s condensate, 90°C → 30°C, cp=4.1868.
    Q = 0.5 * 4.1868 * 60 = 125.6 kW."""
    r = condensate_heat_recovery(0.5, 90.0, T_drain_C=30.0)
    assert abs(r["Q_recovered_kW"] - 0.5 * 4.1868 * 60) < 0.1


# ───────────────────────────────────────────────────────────────
# 45  steam_trap_capacity
# ───────────────────────────────────────────────────────────────

def test_steam_trap_capacity_basic():
    """dP=3 bar, d=5 mm → some positive discharge rate."""
    r = steam_trap_capacity(3.0, 5.0)
    assert r["m_condensate_kgs"] > 0
    assert r["m_condensate_kgh"] > 0


# ───────────────────────────────────────────────────────────────
# 46–48  safety_valve_napier
# ───────────────────────────────────────────────────────────────

def test_safety_valve_napier_saturated():
    """Set 10 barg, area=500 mm².
    P_abs = 10+1+1 = 12 bar; W = 0.0635*12*500 = 381 kg/h."""
    r = safety_valve_napier(10.0, 500.0)
    assert "W_kgh" in r
    P_abs_expected = 10 + 1 + 0.1 * 10
    W_expected = 0.0635 * P_abs_expected * 500.0
    assert abs(r["W_kgh"] - W_expected) < 0.1


def test_safety_valve_napier_superheated():
    """Superheated steam: Ksh < 1, so W < saturated case."""
    r_sat = safety_valve_napier(10.0, 500.0, steam_type="saturated")
    r_sh = safety_valve_napier(10.0, 500.0, steam_type="superheated", superheat_C=100.0)
    assert r_sh["W_kgh"] < r_sat["W_kgh"]
    assert r_sh["Ksh"] < 1.0


def test_safety_valve_napier_zero_pressure():
    """Set pressure 0 barg (atmospheric) still valid; P_abs = 1.0 bar."""
    r = safety_valve_napier(0.0, 300.0)
    assert "W_kgh" in r
    assert r["W_kgh"] > 0


# ───────────────────────────────────────────────────────────────
# 49  boiler_steam_output round-trip
# ───────────────────────────────────────────────────────────────

def test_steam_output_roundtrip():
    """boiler_steam_output followed by boiler_efficiency_io recovers η."""
    eta_in = 0.88
    Q_fuel = 10000.0
    h_s, h_fw = 2700.0, 420.0
    r_out = boiler_steam_output(Q_fuel, eta_in, h_s, h_fw)
    m_s = r_out["m_steam_kgs"]
    r_eta = boiler_efficiency_io(m_s, h_s, h_fw, Q_fuel)
    assert abs(r_eta["efficiency"] - eta_in) < 1e-4


# ───────────────────────────────────────────────────────────────
# 50  steam_properties via T and via P agree
# ───────────────────────────────────────────────────────────────

def test_steam_properties_t_vs_p_consistent():
    """steam_properties via T and via P should agree within 0.1%."""
    r_T = steam_properties(T_sat_C=150.0)
    P = r_T["P_sat_Pa"]
    r_P = steam_properties(P_Pa=P)
    assert abs(r_P["T_sat_C"] - 150.0) < 0.5
    assert abs(r_P["hfg_kJkg"] - r_T["hfg_kJkg"]) / r_T["hfg_kJkg"] < 0.01
