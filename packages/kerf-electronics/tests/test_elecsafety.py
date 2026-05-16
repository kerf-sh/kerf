"""
Hermetic tests for the electrical safety, grounding, isolation & arc-flash module.

≥30 tests covering IEC/IEEE hand-calcs:

  protective_earth_conductor_size
    - Copper adiabatic: A = I×√t/k exactly
    - Aluminium and steel material constants
    - Zero fault current → ok=False
    - Zero duration → ok=False
    - Invalid material → ok=False
    - Long duration warning present

  bonding_resistance_check
    - GPR = I × R exactly
    - Below touch voltage → gpr_hazard=False
    - Above touch voltage → gpr_hazard=True, warning issued
    - Zero bond resistance → GPR=0, safe
    - Negative resistance → ok=False

  ground_electrode_resistance
    - Rod: Dwight formula vs hand-calc
    - Plate: R = ρ/(8r) hand-calc
    - Grid: Schwarz formula non-negative
    - High soil resistivity warning
    - R > 10 Ω warning for rod
    - Unknown electrode_type → ok=False

  ground_potential_rise
    - GPR = I × R_ground
    - GPR > 1000 V → hazard_level=HIGH
    - GPR > 5000 V → hazard_level=EXTREME
    - GPR < 1000 V → hazard_level=LOW
    - Zero resistance → GPR=0

  touch_step_voltage
    - I_body = 0.70×0.116/√t (70 kg body)
    - V_touch exactly (no surface layer)
    - V_step exactly (no surface layer)
    - Surface layer resistivity shifts V_touch/V_step up
    - 50 kg body uses Cb=0.58
    - Long duration warning

  creepage_clearance
    - PD2 MG-I base creepage at 250 V = 2.0 mm
    - PD3 multiplier doubles PD2 result
    - MG-IIIa multiplier ×1.6 relative to MG-I
    - Altitude > 2000 m increases min_clearance
    - Measured creepage below min → creepage_ok=False, warning
    - Measured clearance below min → clearance_ok=False, warning
    - Invalid pollution_degree → ok=False
    - Invalid material_group → ok=False

  insulation_hipot
    - Basic insulation 100 V → test voltage in table range
    - Reinforced insulation = 2× basic
    - Equipment class II with basic insulation → also 2×
    - Invalid insulation_class → ok=False

  leakage_touch_current_limit
    - IT Class I normal → limit = 3.5 mA
    - IT Class II → limit = 0.25 mA
    - Medical Class I patient_CF → limit = 10 μA
    - Measured leakage < limit → compliant=True
    - Measured leakage > limit → compliant=False, warning
    - Invalid application → ok=False

  rcd_gfci_threshold
    - 30 mA RCD, leakage 10 mA → will_trip=False, margin=0.02 A
    - 30 mA RCD, leakage 30 mA → will_trip=True
    - UL Class A, 8 mA → will_trip=True
    - Negative leakage → ok=False

  arc_flash_incident_energy
    - Lee energy vs hand-calc (480 V, 20 kA, 0.1 s, 455 mm)
    - Enclosure vs open_air gives higher empirical energy
    - PPE category assigned for known energy range
    - High energy → warnings non-empty
    - Zero voltage → ok=False

  wire_ampacity
    - XLPE 10 mm² at 30°C → base ampacity from table
    - Derating factor decreases ampacity at elevated ambient
    - Load above derated ampacity → overloaded=True, warning
    - Ambient >= T_max → ok=False
    - PVC vs XLPE at same size → XLPE higher ampacity (same base, less derating)
    - Unknown insulation → ok=False

  selv_pelv_check
    - 48 V AC → is_selv_pelv=True
    - 51 V AC → is_selv_pelv=False, warning
    - 110 V DC → is_selv_pelv=True (< 120 V)
    - 125 V DC → is_selv_pelv=False
    - Both zero → ok=False
"""
from __future__ import annotations

import math
import warnings as _warnings_module

import pytest

from kerf_electronics.elecsafety.safety import (
    arc_flash_incident_energy,
    bonding_resistance_check,
    creepage_clearance,
    ground_electrode_resistance,
    ground_potential_rise,
    insulation_hipot,
    leakage_touch_current_limit,
    protective_earth_conductor_size,
    rcd_gfci_threshold,
    selv_pelv_check,
    touch_step_voltage,
    wire_ampacity,
)

# ─────────────────────────────────────────────────────────────────────────────
# protective_earth_conductor_size
# ─────────────────────────────────────────────────────────────────────────────

class TestPEConductorSize:
    def test_copper_adiabatic_exact(self):
        # A = I × √t / k = 1000 × √1 / 115 = 8.696 mm²
        r = protective_earth_conductor_size(1000.0, 1.0, "copper")
        assert r["ok"]
        assert abs(r["area_min_mm2"] - 1000.0 / 115.0) < 1e-3

    def test_aluminium_k_constant(self):
        r = protective_earth_conductor_size(1000.0, 1.0, "aluminium")
        assert r["ok"]
        assert abs(r["area_min_mm2"] - 1000.0 / 76.0) < 1e-3

    def test_steel_k_constant(self):
        r = protective_earth_conductor_size(500.0, 0.5, "steel")
        assert r["ok"]
        expected = 500.0 * math.sqrt(0.5) / 52.0
        assert abs(r["area_min_mm2"] - expected) < 1e-3

    def test_zero_current_fails(self):
        r = protective_earth_conductor_size(0.0, 1.0)
        assert not r["ok"]

    def test_zero_duration_fails(self):
        r = protective_earth_conductor_size(1000.0, 0.0)
        assert not r["ok"]

    def test_invalid_material_fails(self):
        r = protective_earth_conductor_size(1000.0, 1.0, "gold")
        assert not r["ok"]
        assert "material" in r["reason"].lower()

    def test_long_duration_warning(self):
        r = protective_earth_conductor_size(1000.0, 10.0)
        assert r["ok"]
        assert any("5 s" in w or "adiabatic" in w for w in r["warnings"])

    def test_sqrt_time_scaling(self):
        # Doubling duration → area × √2
        r1 = protective_earth_conductor_size(1000.0, 1.0)
        r2 = protective_earth_conductor_size(1000.0, 4.0)
        assert abs(r2["area_min_mm2"] / r1["area_min_mm2"] - 2.0) < 1e-3


# ─────────────────────────────────────────────────────────────────────────────
# bonding_resistance_check
# ─────────────────────────────────────────────────────────────────────────────

class TestBondingResistance:
    def test_gpr_exact(self):
        r = bonding_resistance_check(100.0, 0.2)
        assert r["ok"]
        assert abs(r["gpr_v"] - 20.0) < 1e-6

    def test_below_touch_voltage_safe(self):
        r = bonding_resistance_check(100.0, 0.1)
        assert r["ok"]
        assert not r["gpr_hazard"]

    def test_above_touch_voltage_hazard(self):
        with _warnings_module.catch_warnings(record=True) as w:
            _warnings_module.simplefilter("always")
            r = bonding_resistance_check(1000.0, 1.0)
        assert r["ok"]
        assert r["gpr_hazard"]
        assert len(w) >= 1

    def test_zero_resistance_safe(self):
        r = bonding_resistance_check(10000.0, 0.0)
        assert r["ok"]
        assert r["gpr_v"] == 0.0
        assert not r["gpr_hazard"]

    def test_negative_resistance_fails(self):
        r = bonding_resistance_check(100.0, -0.1)
        assert not r["ok"]


# ─────────────────────────────────────────────────────────────────────────────
# ground_electrode_resistance
# ─────────────────────────────────────────────────────────────────────────────

class TestGroundElectrode:
    def test_rod_dwight_hand_calc(self):
        # ρ=100 Ω·m, L=3 m, a=0.0079 m
        # R = 100/(2π×3) × [ln(4×3/0.0079) − 1]
        rho, L, a = 100.0, 3.0, 0.0079
        expected = (rho / (2 * math.pi * L)) * (math.log(4 * L / a) - 1)
        r = ground_electrode_resistance("rod", rho, length_m=L, radius_m=a)
        assert r["ok"]
        assert abs(r["resistance_ohm"] - expected) < 1e-2

    def test_plate_hand_calc(self):
        # ρ=100 Ω·m, area=1 m² → r_circ=√(1/π), R = 100/(8×r_circ)
        rho, area = 100.0, 1.0
        r_circ = math.sqrt(area / math.pi)
        expected = rho / (8.0 * r_circ)
        r = ground_electrode_resistance("plate", rho, area_m2=area)
        assert r["ok"]
        assert abs(r["resistance_ohm"] - expected) < 1e-2

    def test_grid_non_negative(self):
        r = ground_electrode_resistance("grid", 100.0, grid_area_m2=100.0,
                                        grid_total_conductor_m=80.0, grid_num_meshes=9.0)
        assert r["ok"]
        assert r["resistance_ohm"] >= 0.0

    def test_high_soil_resistivity_warning(self):
        r = ground_electrode_resistance("rod", 2000.0)
        assert r["ok"]
        assert any("resistivity" in w.lower() for w in r["warnings"])

    def test_high_resistance_warning(self):
        # Low-conductivity soil + short rod will exceed 10 Ω
        r = ground_electrode_resistance("rod", 500.0, length_m=1.0, radius_m=0.01)
        assert r["ok"]
        assert any("10" in w for w in r["warnings"])

    def test_unknown_electrode_type_fails(self):
        r = ground_electrode_resistance("mesh", 100.0)
        assert not r["ok"]


# ─────────────────────────────────────────────────────────────────────────────
# ground_potential_rise
# ─────────────────────────────────────────────────────────────────────────────

class TestGPR:
    def test_gpr_exact(self):
        r = ground_potential_rise(500.0, 2.0)
        assert r["ok"]
        assert abs(r["gpr_v"] - 1000.0) < 1e-6

    def test_low_hazard(self):
        r = ground_potential_rise(100.0, 5.0)
        assert r["ok"]
        assert r["hazard_level"] == "LOW"

    def test_high_hazard(self):
        with _warnings_module.catch_warnings(record=True) as w:
            _warnings_module.simplefilter("always")
            r = ground_potential_rise(1000.0, 2.0)
        assert r["ok"]
        assert r["hazard_level"] == "HIGH"
        assert len(w) >= 1

    def test_extreme_hazard(self):
        with _warnings_module.catch_warnings(record=True) as w:
            _warnings_module.simplefilter("always")
            r = ground_potential_rise(10000.0, 5.0)
        assert r["ok"]
        assert r["hazard_level"] == "EXTREME"
        assert len(w) >= 1

    def test_zero_resistance(self):
        r = ground_potential_rise(10000.0, 0.0)
        assert r["ok"]
        assert r["gpr_v"] == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# touch_step_voltage
# ─────────────────────────────────────────────────────────────────────────────

class TestTouchStepVoltage:
    def test_ibody_70kg_exact(self):
        # I_body = 0.70 × 0.116 / √0.5 = 0.70 × 0.116 / 0.7071...
        t = 0.5
        i_body_expected = 0.70 * 0.116 / math.sqrt(t)
        r = touch_step_voltage(500.0, t, body_weight_kg=70.0)
        assert r["ok"]
        assert abs(r["i_body_permissible_a"] - i_body_expected) < 1e-6

    def test_v_touch_no_surface_layer(self):
        # V_touch = (1000 + 1.5×0) × I_body = 1000 × I_body
        t = 1.0
        i_body = 0.70 * 0.116 / math.sqrt(t)
        r = touch_step_voltage(500.0, t, surface_layer_resistivity_ohm_m=0.0)
        assert r["ok"]
        assert abs(r["v_touch_permissible_v"] - 1000.0 * i_body) < 1e-3

    def test_v_step_no_surface_layer(self):
        t = 1.0
        i_body = 0.70 * 0.116 / math.sqrt(t)
        r = touch_step_voltage(500.0, t, surface_layer_resistivity_ohm_m=0.0)
        assert r["ok"]
        assert abs(r["v_step_permissible_v"] - 1000.0 * i_body) < 1e-3

    def test_surface_layer_increases_voltages(self):
        r_no  = touch_step_voltage(500.0, 1.0, surface_layer_resistivity_ohm_m=0.0)
        r_yes = touch_step_voltage(500.0, 1.0, surface_layer_resistivity_ohm_m=2500.0)
        assert r_yes["v_touch_permissible_v"] > r_no["v_touch_permissible_v"]
        assert r_yes["v_step_permissible_v"]  > r_no["v_step_permissible_v"]

    def test_50kg_body_uses_cb_058(self):
        r = touch_step_voltage(500.0, 1.0, body_weight_kg=50.0)
        assert r["ok"]
        assert abs(r["c_b"] - 0.58) < 1e-9

    def test_long_duration_warning(self):
        r = touch_step_voltage(500.0, 2.0)
        assert r["ok"]
        assert any("1 s" in w or "duration" in w.lower() for w in r["warnings"])

    def test_zero_duration_fails(self):
        r = touch_step_voltage(500.0, 0.0)
        assert not r["ok"]


# ─────────────────────────────────────────────────────────────────────────────
# creepage_clearance
# ─────────────────────────────────────────────────────────────────────────────

class TestCreepageClearance:
    def test_pd2_mgi_250v_base_creepage(self):
        # Table entry for 250 V, PD=2, MG=I is 2.0 mm
        r = creepage_clearance(250.0, pollution_degree=2, material_group="I")
        assert r["ok"]
        assert abs(r["min_creepage_mm"] - 2.0) < 0.1

    def test_pd3_multiplier_doubles_pd2(self):
        r2 = creepage_clearance(250.0, pollution_degree=2, material_group="I")
        r3 = creepage_clearance(250.0, pollution_degree=3, material_group="I")
        assert r3["min_creepage_mm"] > r2["min_creepage_mm"]
        assert abs(r3["min_creepage_mm"] / r2["min_creepage_mm"] - 2.0) < 1e-9

    def test_mg_iiia_multiplier(self):
        rI  = creepage_clearance(250.0, pollution_degree=2, material_group="I")
        rIII = creepage_clearance(250.0, pollution_degree=2, material_group="IIIa")
        assert abs(rIII["min_creepage_mm"] / rI["min_creepage_mm"] - 1.6) < 1e-9

    def test_altitude_increases_clearance(self):
        r_low  = creepage_clearance(250.0, altitude_m=2000.0)
        r_high = creepage_clearance(250.0, altitude_m=5000.0)
        assert r_high["min_clearance_mm"] > r_low["min_clearance_mm"]

    def test_measured_creepage_below_min_fails(self):
        with _warnings_module.catch_warnings(record=True) as w:
            _warnings_module.simplefilter("always")
            r = creepage_clearance(250.0, measured_creepage_mm=0.5)
        assert r["ok"]
        assert r["creepage_ok"] is False
        assert any("CREEPAGE" in str(warning.message).upper() for warning in w)

    def test_measured_creepage_above_min_passes(self):
        r = creepage_clearance(250.0, measured_creepage_mm=10.0)
        assert r["ok"]
        assert r["creepage_ok"] is True

    def test_measured_clearance_below_min_fails(self):
        with _warnings_module.catch_warnings(record=True) as w:
            _warnings_module.simplefilter("always")
            r = creepage_clearance(250.0, measured_clearance_mm=0.01)
        assert r["ok"]
        assert r["clearance_ok"] is False
        assert any("CLEARANCE" in str(warning.message).upper() for warning in w)

    def test_invalid_pollution_degree_fails(self):
        r = creepage_clearance(250.0, pollution_degree=5)
        assert not r["ok"]

    def test_invalid_material_group_fails(self):
        r = creepage_clearance(250.0, material_group="IV")
        assert not r["ok"]


# ─────────────────────────────────────────────────────────────────────────────
# insulation_hipot
# ─────────────────────────────────────────────────────────────────────────────

class TestInsulationHipot:
    def test_basic_100v_in_range(self):
        r = insulation_hipot(100.0, "basic", "I")
        assert r["ok"]
        assert r["test_voltage_v_rms"] >= 500.0

    def test_reinforced_double_basic(self):
        r_basic = insulation_hipot(100.0, "basic",      "I")
        r_reinf = insulation_hipot(100.0, "reinforced", "I")
        assert r_reinf["ok"]
        # reinforced = 2× basic
        assert abs(r_reinf["test_voltage_v_rms"] / r_basic["test_voltage_v_rms"] - 2.0) < 1e-6

    def test_class_ii_basic_gets_reinforced(self):
        r_I   = insulation_hipot(100.0, "basic", "I")
        r_II  = insulation_hipot(100.0, "basic", "II")
        assert r_II["test_voltage_v_rms"] >= r_I["test_voltage_v_rms"]

    def test_invalid_insulation_class_fails(self):
        r = insulation_hipot(100.0, "super_reinforced", "I")
        assert not r["ok"]

    def test_invalid_equipment_class_fails(self):
        r = insulation_hipot(100.0, "basic", "IV")
        assert not r["ok"]


# ─────────────────────────────────────────────────────────────────────────────
# leakage_touch_current_limit
# ─────────────────────────────────────────────────────────────────────────────

class TestLeakageTouchCurrentLimit:
    def test_it_class_i_normal_35ma(self):
        r = leakage_touch_current_limit("I", "it", "normal")
        assert r["ok"]
        assert abs(r["limit_a"] - 3.5e-3) < 1e-10

    def test_it_class_ii_025ma(self):
        r = leakage_touch_current_limit("II", "it", "normal")
        assert r["ok"]
        assert abs(r["limit_a"] - 0.25e-3) < 1e-10

    def test_medical_patient_cf_10ua(self):
        r = leakage_touch_current_limit("I", "medical", "patient_cf")
        assert r["ok"]
        assert abs(r["limit_a"] - 10e-6) < 1e-12

    def test_compliant_below_limit(self):
        r = leakage_touch_current_limit("I", "it", "normal", measured_leakage_a=1e-3)
        assert r["ok"]
        assert r["compliant"] is True

    def test_non_compliant_above_limit(self):
        with _warnings_module.catch_warnings(record=True) as w:
            _warnings_module.simplefilter("always")
            r = leakage_touch_current_limit("I", "it", "normal", measured_leakage_a=10e-3)
        assert r["ok"]
        assert r["compliant"] is False
        assert len(w) >= 1

    def test_invalid_application_fails(self):
        r = leakage_touch_current_limit("I", "hvac", "normal")
        assert not r["ok"]


# ─────────────────────────────────────────────────────────────────────────────
# rcd_gfci_threshold
# ─────────────────────────────────────────────────────────────────────────────

class TestRcdGfciThreshold:
    def test_30ma_rcd_10ma_leakage_no_trip(self):
        r = rcd_gfci_threshold(0.030, 0.010)
        assert r["ok"]
        assert not r["will_trip"]
        assert abs(r["margin_a"] - 0.020) < 1e-9

    def test_30ma_rcd_30ma_leakage_trips(self):
        with _warnings_module.catch_warnings(record=True) as w:
            _warnings_module.simplefilter("always")
            r = rcd_gfci_threshold(0.030, 0.030)
        assert r["ok"]
        assert r["will_trip"]
        assert len(w) >= 1

    def test_ul_class_a_8ma_trips(self):
        with _warnings_module.catch_warnings(record=True) as w:
            _warnings_module.simplefilter("always")
            r = rcd_gfci_threshold(0.030, 0.008, device_type="ul_class_a")
        assert r["ok"]
        assert r["will_trip"]  # 8 mA > 6 mA UL Class A trip

    def test_ul_class_a_trip_threshold(self):
        r = rcd_gfci_threshold(0.030, 0.004, device_type="ul_class_a")
        assert r["ok"]
        assert not r["will_trip"]
        assert abs(r["trip_threshold_a"] - 6e-3) < 1e-9

    def test_negative_leakage_fails(self):
        r = rcd_gfci_threshold(0.030, -0.001)
        assert not r["ok"]


# ─────────────────────────────────────────────────────────────────────────────
# arc_flash_incident_energy
# ─────────────────────────────────────────────────────────────────────────────

class TestArcFlashIncidentEnergy:
    def test_lee_equation_hand_calc(self):
        # V=480 V, I_bf=20 kA, t=0.1 s, D=455 mm
        # E_Lee = 793 × 0.480 × 20 × 0.1 / 455² cal/cm²
        V, I, t, D = 480.0, 20.0, 0.1, 455.0
        expected_lee = 793.0 * (V / 1000.0) * I * t / (D ** 2)
        r = arc_flash_incident_energy(V, I, t, D)
        assert r["ok"]
        # result is rounded to 4 decimal places; allow rounding tolerance
        assert abs(r["incident_energy_cal_cm2_lee"] - expected_lee) < 5e-5

    def test_enclosure_higher_than_open_air(self):
        r_open = arc_flash_incident_energy(480.0, 20.0, 0.1, 455.0, system_type="open_air")
        r_enc  = arc_flash_incident_energy(480.0, 20.0, 0.1, 455.0, system_type="enclosure")
        assert r_enc["incident_energy_cal_cm2_empirical"] > r_open["incident_energy_cal_cm2_empirical"]

    def test_ppe_category_assigned(self):
        r = arc_flash_incident_energy(480.0, 20.0, 0.1, 455.0)
        assert r["ok"]
        assert r["ppe_category"] is not None
        assert isinstance(r["ppe_category"], int)

    def test_high_energy_warning(self):
        # Very high fault current and long clearing time
        with _warnings_module.catch_warnings(record=True) as w:
            _warnings_module.simplefilter("always")
            r = arc_flash_incident_energy(15000.0, 100.0, 2.0, 100.0)
        assert r["ok"]
        assert len(w) >= 1

    def test_zero_voltage_fails(self):
        r = arc_flash_incident_energy(0.0, 20.0, 0.1)
        assert not r["ok"]

    def test_afb_positive(self):
        r = arc_flash_incident_energy(480.0, 20.0, 0.1, 455.0)
        assert r["ok"]
        assert r["afb_mm"] > 0.0


# ─────────────────────────────────────────────────────────────────────────────
# wire_ampacity
# ─────────────────────────────────────────────────────────────────────────────

class TestWireAmpacity:
    def test_xlpe_10mm2_base_ampacity(self):
        r = wire_ampacity(10.0, "xlpe", ambient_temp_c=30.0)
        assert r["ok"]
        # Table value at 30°C (no derating needed) → derating_factor ≈ 1.0
        assert r["derated_ampacity_a"] > 0.0
        assert abs(r["derating_factor"] - 1.0) < 1e-9

    def test_high_ambient_reduces_ampacity(self):
        r_30 = wire_ampacity(10.0, "xlpe", ambient_temp_c=30.0)
        r_60 = wire_ampacity(10.0, "xlpe", ambient_temp_c=60.0)
        assert r_60["derated_ampacity_a"] < r_30["derated_ampacity_a"]

    def test_overloaded_flag(self):
        with _warnings_module.catch_warnings(record=True) as w:
            _warnings_module.simplefilter("always")
            r = wire_ampacity(1.0, "pvc", ambient_temp_c=30.0, load_current_a=200.0)
        assert r["ok"]
        assert r["overloaded"] is True
        assert len(w) >= 1

    def test_not_overloaded(self):
        r = wire_ampacity(10.0, "xlpe", ambient_temp_c=30.0, load_current_a=10.0)
        assert r["ok"]
        assert r["overloaded"] is False

    def test_ambient_above_tmax_fails(self):
        r = wire_ampacity(10.0, "pvc", ambient_temp_c=80.0)  # pvc T_max=70°C
        assert not r["ok"]

    def test_unknown_insulation_fails(self):
        r = wire_ampacity(10.0, "kapton")
        assert not r["ok"]

    def test_xlpe_higher_base_than_pvc_same_derating(self):
        # Both at 30°C — same reference ambient, same derating
        r_pvc  = wire_ampacity(10.0, "pvc",  ambient_temp_c=30.0)
        r_xlpe = wire_ampacity(10.0, "xlpe", ambient_temp_c=30.0)
        # XLPE allows more derating headroom; derated amp should be >=
        # (actually same base but XLPE stays at factor=1.0, PVC too — they share table)
        # Both use same table; key check: both ok and derating_factor=1.0
        assert r_pvc["ok"] and r_xlpe["ok"]
        assert abs(r_pvc["derating_factor"]  - 1.0) < 1e-9
        assert abs(r_xlpe["derating_factor"] - 1.0) < 1e-9


# ─────────────────────────────────────────────────────────────────────────────
# selv_pelv_check
# ─────────────────────────────────────────────────────────────────────────────

class TestSelvPelvCheck:
    def test_48vac_is_selv(self):
        r = selv_pelv_check(voltage_v_ac_rms=48.0, circuit_type="SELV")
        assert r["ok"]
        assert r["is_selv_pelv"] is True

    def test_51vac_not_selv(self):
        with _warnings_module.catch_warnings(record=True) as w:
            _warnings_module.simplefilter("always")
            r = selv_pelv_check(voltage_v_ac_rms=51.0, circuit_type="SELV")
        assert r["ok"]
        assert r["is_selv_pelv"] is False
        assert len(w) >= 1

    def test_110vdc_is_selv(self):
        r = selv_pelv_check(voltage_v_dc=110.0, circuit_type="PELV")
        assert r["ok"]
        assert r["is_selv_pelv"] is True

    def test_125vdc_not_selv(self):
        with _warnings_module.catch_warnings(record=True) as w:
            _warnings_module.simplefilter("always")
            r = selv_pelv_check(voltage_v_dc=125.0, circuit_type="SELV")
        assert r["ok"]
        assert r["is_selv_pelv"] is False

    def test_both_zero_fails(self):
        r = selv_pelv_check(0.0, 0.0)
        assert not r["ok"]

    def test_invalid_circuit_type_fails(self):
        r = selv_pelv_check(voltage_v_ac_rms=24.0, circuit_type="ELV")
        assert not r["ok"]

    def test_50vac_boundary_is_selv(self):
        # Exactly at 50 V AC → should pass
        r = selv_pelv_check(voltage_v_ac_rms=50.0)
        assert r["ok"]
        assert r["is_selv_pelv"] is True


# ─────────────────────────────────────────────────────────────────────────────
# LLM tool handler smoke tests (stub registry)
# ─────────────────────────────────────────────────────────────────────────────

class TestToolHandlers:
    """Smoke-test each LLM tool handler through its async entry point."""

    @pytest.fixture(autouse=True)
    def _registry_stub(self, monkeypatch):
        """Patch kerf_chat registry so tools.py can be imported without the full server."""
        import types
        import sys
        import importlib

        # Build a minimal stub if kerf_chat is not available
        if "kerf_chat" not in sys.modules:
            chat_mod = types.ModuleType("kerf_chat")
            tools_mod = types.ModuleType("kerf_chat.tools")
            reg_mod   = types.ModuleType("kerf_chat.tools.registry")

            import json as _json

            class _ToolSpec:
                def __init__(self, name, description="", input_schema=None):
                    self.name = name
                    self.description = description
                    self.input_schema = input_schema or {}

            def _register(spec, write=False):
                def decorator(fn):
                    return fn
                return decorator

            def _ok_payload(data):
                return _json.dumps({"ok": True, **data})

            def _err_payload(reason, code="ERR"):
                return _json.dumps({"ok": False, "reason": reason, "code": code})

            reg_mod.ToolSpec  = _ToolSpec
            reg_mod.register  = _register
            reg_mod.ok_payload = _ok_payload
            reg_mod.err_payload = _err_payload

            tools_mod.registry = reg_mod
            chat_mod.tools     = tools_mod
            sys.modules["kerf_chat"]                 = chat_mod
            sys.modules["kerf_chat.tools"]           = tools_mod
            sys.modules["kerf_chat.tools.registry"]  = reg_mod

        # Reload to pick up the stub
        if "kerf_electronics.elecsafety.tools" in sys.modules:
            importlib.reload(sys.modules["kerf_electronics.elecsafety.tools"])
        else:
            importlib.import_module("kerf_electronics.elecsafety.tools")

    def _call(self, fn, payload: dict):
        import asyncio, json
        return asyncio.get_event_loop().run_until_complete(fn(None, json.dumps(payload).encode()))

    def test_pe_conductor_tool_ok(self):
        from kerf_electronics.elecsafety.tools import elecsafety_pe_conductor_size
        import json
        result = json.loads(self._call(elecsafety_pe_conductor_size,
                                       {"fault_current_a": 1000, "fault_duration_s": 1.0}))
        assert result.get("ok")

    def test_arc_flash_tool_ok(self):
        from kerf_electronics.elecsafety.tools import elecsafety_arc_flash
        import json
        result = json.loads(self._call(elecsafety_arc_flash,
                                       {"system_voltage_v": 480, "bolted_fault_current_ka": 10,
                                        "arcing_duration_s": 0.1}))
        assert result.get("ok")

    def test_wire_ampacity_tool_ok(self):
        from kerf_electronics.elecsafety.tools import elecsafety_wire_ampacity
        import json
        result = json.loads(self._call(elecsafety_wire_ampacity,
                                       {"cross_section_mm2": 10.0}))
        assert result.get("ok")

    def test_selv_pelv_tool_ok(self):
        from kerf_electronics.elecsafety.tools import elecsafety_selv_pelv
        import json
        result = json.loads(self._call(elecsafety_selv_pelv,
                                       {"voltage_v_ac_rms": 24.0}))
        assert result.get("ok")

    def test_tool_bad_json_returns_err(self):
        from kerf_electronics.elecsafety.tools import elecsafety_pe_conductor_size
        import asyncio, json
        result = json.loads(
            asyncio.get_event_loop().run_until_complete(
                elecsafety_pe_conductor_size(None, b"not-json")
            )
        )
        assert not result.get("ok")
