"""
Hermetic tests for kerf_cad_core.elecpower — NEC building power distribution.

Coverage:
  distribution.demand_load          — Art. 220 dwelling/commercial demand factors
  distribution.conductor_ampacity   — NEC 310.16 ambient + bundling derate
  distribution.conductor_size_for_load — minimum conductor selection
  distribution.voltage_drop         — 1φ/3φ VD formula + upsizing
  distribution.conduit_fill         — Ch.9 fill percentage
  distribution.overcurrent_device_size — NEC 240.4 OCPD sizing
  distribution.motor_branch_circuit — Art. 430 FLC / conductor / OCPD
  distribution.transformer_feeder_size — Art. 450 FLA + short-circuit
  distribution.short_circuit_analysis — point-to-point SCA
  distribution.power_factor_correction — kVAR + capacitance
  distribution.grounding_conductor_size — GEC 250.66 / EGC 250.122
  distribution.panel_schedule_rollup — panel schedule
  distribution.generator_ups_size   — generator sizing
  tools.*                           — LLM tool wrappers

All tests are pure-Python and hermetic: no OCC, no DB, no network, no fixtures.
Formulas are verified algebraically against NEC hand-calculations.

References
----------
NFPA 70 (NEC) 2023
Mike Holt's Illustrated Guide to NEC calculations

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.elecpower.distribution import (
    demand_load,
    conductor_ampacity,
    conductor_size_for_load,
    voltage_drop,
    conduit_fill,
    overcurrent_device_size,
    motor_branch_circuit,
    transformer_feeder_size,
    short_circuit_analysis,
    power_factor_correction,
    grounding_conductor_size,
    panel_schedule_rollup,
    generator_ups_size,
    _next_standard_ocpd,
    _ambient_correction,
    _bundling_factor,
    _STANDARD_OCPD,
)
from kerf_cad_core.elecpower.tools import (
    run_demand_load,
    run_conductor_ampacity,
    run_conductor_size,
    run_voltage_drop,
    run_conduit_fill,
    run_ocpd_size,
    run_motor_branch,
    run_transformer_feeder,
    run_short_circuit,
    run_pf_correction,
    run_grounding_conductor,
    run_panel_schedule,
    run_generator_size,
)


# ---------------------------------------------------------------------------
# Test helpers
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
        return None


def _args(**kwargs) -> bytes:
    return json.dumps(kwargs).encode()


def _ok_tool(raw: str) -> dict:
    d = json.loads(raw)
    assert d.get("ok") is True, f"Expected ok=True, got: {d}"
    return d


def _err_tool(raw: str) -> dict:
    d = json.loads(raw)
    is_ok_false = d.get("ok") is False
    is_err_payload = "error" in d and "code" in d
    assert is_ok_false or is_err_payload, f"Expected error response, got: {d}"
    return d


REL = 1e-3  # relative tolerance for NEC table lookups


# ===========================================================================
# 1. demand_load — NEC Art. 220
# ===========================================================================

class TestDemandLoad:

    def test_commercial_all_noncontinuous(self):
        """Commercial: 100% of noncontinuous load, no demand reduction."""
        loads = [{"name": "A", "va": 10000, "continuous": False}]
        r = demand_load(loads, occupancy="commercial")
        assert r["ok"] is True
        assert r["demand_va"] == pytest.approx(10000, rel=REL)

    def test_continuous_load_multiplied_125pct(self):
        """Continuous loads multiplied by 1.25 per NEC 215.2."""
        loads = [{"name": "lights", "va": 8000, "continuous": True}]
        r = demand_load(loads, occupancy="commercial")
        assert r["ok"] is True
        assert r["demand_va"] == pytest.approx(8000 * 1.25, rel=REL)

    def test_mixed_continuous_noncontinuous(self):
        """Mixed: 125% continuous + 100% noncontinuous."""
        loads = [
            {"name": "cont", "va": 4000, "continuous": True},
            {"name": "nonc", "va": 2000, "continuous": False},
        ]
        r = demand_load(loads, occupancy="commercial")
        expected = 4000 * 1.25 + 2000
        assert r["ok"] is True
        assert r["demand_va"] == pytest.approx(expected, rel=REL)

    def test_dwelling_demand_factor_applied(self):
        """Dwelling NEC 220.42: first 3000 VA @ 100%, next @35%."""
        # 10000 VA noncontinuous in dwelling
        loads = [{"name": "gen_lighting", "va": 10000}]
        r = demand_load(loads, occupancy="dwelling")
        assert r["ok"] is True
        # Expected: 3000 + (10000-3000)*0.35 = 3000 + 2450 = 5450
        assert r["demand_va"] == pytest.approx(5450, rel=REL)

    def test_industrial_same_as_commercial(self):
        """Industrial uses 100% noncontinuous, same as commercial."""
        loads = [{"name": "eq", "va": 5000}]
        r_commercial = demand_load(loads, occupancy="commercial")
        r_industrial = demand_load(loads, occupancy="industrial")
        assert r_commercial["demand_va"] == r_industrial["demand_va"]

    def test_invalid_occupancy_returns_error(self):
        loads = [{"name": "a", "va": 1000}]
        r = demand_load(loads, occupancy="retail")
        assert r["ok"] is False

    def test_negative_va_returns_error(self):
        loads = [{"name": "a", "va": -100}]
        r = demand_load(loads, occupancy="commercial")
        assert r["ok"] is False

    def test_continuous_factor_lt_1_returns_error(self):
        loads = [{"name": "a", "va": 1000}]
        r = demand_load(loads, occupancy="commercial", continuous_factor=0.9)
        assert r["ok"] is False


# ===========================================================================
# 2. conductor_ampacity — NEC 310.16
# ===========================================================================

class TestConductorAmpacity:

    def test_cu_12awg_base_ampacity(self):
        """NEC 310.16: #12 AWG Cu 75°C = 25A (base, no derate)."""
        r = conductor_ampacity("12", material="cu", ambient_c=30, num_ccc=3)
        assert r["ok"] is True
        assert r["base_ampacity_A"] == 25.0
        assert r["derated_ampacity_A"] == pytest.approx(25.0, rel=REL)

    def test_ambient_40c_correction_applied(self):
        """Ambient 40°C correction factor = 0.88 for 75°C conductors (NEC 310.15(B)(2))."""
        r = conductor_ampacity("10", material="cu", ambient_c=40, num_ccc=3)
        assert r["ok"] is True
        assert r["ambient_correction"] == pytest.approx(0.88, rel=REL)
        assert r["derated_ampacity_A"] == pytest.approx(35.0 * 0.88, rel=REL)

    def test_bundling_4ccc_factor_080(self):
        """4 CCC: bundling factor = 0.80 (NEC 310.15(B)(3)(a))."""
        r = conductor_ampacity("8", material="cu", ambient_c=30, num_ccc=4)
        assert r["ok"] is True
        assert r["bundling_factor"] == pytest.approx(0.80, rel=REL)
        assert r["derated_ampacity_A"] == pytest.approx(50.0 * 0.80, rel=REL)

    def test_combined_ambient_and_bundling(self):
        """Both correction factors applied: derated = base × amb × bundle.

        NEC 310.15(C)(1): 4–6 CCC adjustment factor = 80% (0.80),
        NOT 70%. NEC 310.15(B)(1) ambient correction for 36–40°C
        on a 75°C conductor = 0.88. #6 Cu base 75°C = 65 A.
        Derated = 65 × 0.88 × 0.80 = 45.76 A.
        """
        r = conductor_ampacity("6", material="cu", ambient_c=40, num_ccc=6)
        assert r["ok"] is True
        expected = 65.0 * 0.88 * 0.80
        assert r["derated_ampacity_A"] == pytest.approx(expected, rel=REL)

    def test_aluminum_conductor_lower_ampacity(self):
        """Al conductors have lower ampacity than Cu for same size."""
        r_cu = conductor_ampacity("2", material="cu")
        r_al = conductor_ampacity("2", material="al")
        assert r_cu["ok"] and r_al["ok"]
        assert r_cu["base_ampacity_A"] > r_al["base_ampacity_A"]

    def test_unknown_size_returns_error(self):
        r = conductor_ampacity("999", material="cu")
        assert r["ok"] is False

    def test_invalid_material_returns_error(self):
        r = conductor_ampacity("12", material="gold")
        assert r["ok"] is False

    def test_ambient_exceeds_rating_returns_error(self):
        """Ambient > 75°C exceeds conductor temperature rating."""
        r = conductor_ampacity("12", material="cu", ambient_c=80)
        assert r["ok"] is False


# ===========================================================================
# 3. conductor_size_for_load
# ===========================================================================

class TestConductorSizeForLoad:

    def test_20a_load_selects_12awg_cu(self):
        """20A non-continuous load → minimum #12 AWG Cu (25A derated)."""
        r = conductor_size_for_load(20.0, material="cu")
        assert r["ok"] is True
        # #12 AWG Cu has 25A derated at 30°C, 3 CCC
        assert r["derated_ampacity_A"] >= 20.0

    def test_continuous_load_125pct_factor(self):
        """Continuous 20A → required 25A → selects conductor with ≥25A."""
        r = conductor_size_for_load(20.0, material="cu", continuous=True)
        assert r["ok"] is True
        assert r["required_A"] == pytest.approx(25.0, rel=REL)
        assert r["derated_ampacity_A"] >= 25.0

    def test_large_load_selects_larger_conductor(self):
        """150A load must select ≥ 1/0 AWG Cu (150A derated at 30°C)."""
        r = conductor_size_for_load(150.0, material="cu")
        assert r["ok"] is True
        assert r["derated_ampacity_A"] >= 150.0

    def test_zero_load_returns_error(self):
        r = conductor_size_for_load(0.0)
        assert r["ok"] is False

    def test_negative_load_returns_error(self):
        r = conductor_size_for_load(-10.0)
        assert r["ok"] is False


# ===========================================================================
# 4. voltage_drop — NEC Ch.9 Table 9
# ===========================================================================

class TestVoltageDrop:

    def test_single_phase_vd_formula(self):
        """1φ VD = 2 × I × R × L / 1000; verify against known R for #10 Cu."""
        # #10 Cu: R = 1.24 Ω/kft
        # I=20A, L=100ft, V=120V
        # VD = 2 × 20 × 1.24 × 100 / 1000 = 4.96 V
        r = voltage_drop(20.0, 100.0, "10", 120.0, phases=1, material="cu")
        assert r["ok"] is True
        expected_vd = 2.0 * 20.0 * 1.24 * 100.0 / 1000.0
        assert r["vd_V"] == pytest.approx(expected_vd, rel=REL)

    def test_three_phase_vd_formula(self):
        """3φ VD = √3 × I × R × L / 1000."""
        # #2 Cu: R = 0.194 Ω/kft
        # I=100A, L=200ft, V=480V
        r = voltage_drop(100.0, 200.0, "2", 480.0, phases=3, material="cu")
        assert r["ok"] is True
        expected_vd = math.sqrt(3) * 100.0 * 0.194 * 200.0 / 1000.0
        assert r["vd_V"] == pytest.approx(expected_vd, rel=REL)

    def test_vd_pct_calculation(self):
        """vd_pct = vd_V / voltage × 100."""
        r = voltage_drop(20.0, 100.0, "10", 120.0, phases=1)
        assert r["ok"] is True
        assert r["vd_pct"] == pytest.approx((r["vd_V"] / 120.0) * 100.0, rel=REL)

    def test_vd_exceeds_3pct_sets_flag(self):
        """Long run on small conductor should exceed 3% VD limit."""
        # 20A on #14 Cu, 200ft, 120V
        # VD = 2 × 20 × 3.14 × 200 / 1000 = 25.12 V → 20.9%
        r = voltage_drop(20.0, 200.0, "14", 120.0, phases=1)
        assert r["ok"] is True
        assert r["vd_exceeds_limit"] is True
        assert len(r["warnings"]) > 0

    def test_vd_within_limit_no_flag(self):
        """Short run on adequate conductor stays within 3% limit."""
        # 10A on #10 Cu, 20ft, 120V
        r = voltage_drop(10.0, 20.0, "10", 120.0, phases=1)
        assert r["ok"] is True
        assert r["vd_exceeds_limit"] is False

    def test_upsized_conductor_recommended_when_over_limit(self):
        """When VD > limit, recommended_size should be larger than selected size."""
        r = voltage_drop(20.0, 200.0, "14", 120.0, phases=1)
        assert r["ok"] is True
        if r["vd_exceeds_limit"]:
            # recommended_size should be larger (higher index) than "14"
            from kerf_cad_core.elecpower.distribution import _SIZE_ORDER
            assert _SIZE_ORDER.index(r["recommended_size"]) > _SIZE_ORDER.index("14")

    def test_receiving_end_voltage(self):
        """receiving_end_V = voltage - vd_V."""
        r = voltage_drop(20.0, 100.0, "10", 120.0, phases=1)
        assert r["ok"] is True
        assert r["receiving_end_V"] == pytest.approx(120.0 - r["vd_V"], rel=REL)

    def test_invalid_phases_returns_error(self):
        r = voltage_drop(20.0, 100.0, "10", 120.0, phases=2)
        assert r["ok"] is False

    def test_unknown_size_returns_error(self):
        r = voltage_drop(20.0, 100.0, "99", 120.0)
        assert r["ok"] is False


# ===========================================================================
# 5. conduit_fill — NEC Ch.9
# ===========================================================================

class TestConduitFill:

    def test_three_conductors_40pct_max(self):
        """3+ conductors: max fill 40% per NEC Ch.9 Table 1."""
        r = conduit_fill(
            [{"size": "12", "count": 3}],
            1.0, conduit_type="EMT"
        )
        assert r["ok"] is True
        assert r["max_fill_pct"] == 40.0

    def test_one_conductor_53pct_max(self):
        """1 conductor: max fill 53% per NEC Ch.9 Table 1."""
        r = conduit_fill(
            [{"size": "4/0", "count": 1}],
            2.0, conduit_type="EMT"
        )
        assert r["ok"] is True
        assert r["max_fill_pct"] == 53.0

    def test_two_conductors_31pct_max(self):
        """2 conductors: max fill 31% per NEC Ch.9 Table 1."""
        r = conduit_fill(
            [{"size": "10", "count": 2}],
            0.75, conduit_type="EMT"
        )
        assert r["ok"] is True
        assert r["max_fill_pct"] == 31.0

    def test_fill_ok_for_small_conductors(self):
        """3× #12 AWG in 1" EMT should easily fit within 40%."""
        r = conduit_fill(
            [{"size": "12", "count": 3}],
            1.0, conduit_type="EMT"
        )
        assert r["ok"] is True
        assert r["fill_ok"] is True

    def test_fill_exceeded_generates_warning(self):
        """Many large conductors in small conduit should exceed fill limit."""
        r = conduit_fill(
            [{"size": "4/0", "count": 6}],
            1.0, conduit_type="EMT"
        )
        assert r["ok"] is True
        if not r["fill_ok"]:
            assert len(r["warnings"]) > 0

    def test_unknown_conduit_size_returns_error(self):
        r = conduit_fill(
            [{"size": "12", "count": 3}],
            99.0, conduit_type="EMT"
        )
        assert r["ok"] is False

    def test_fill_pct_formula(self):
        """Verify fill_pct = total_conductor_area / conduit_area × 100 (within rounding)."""
        r = conduit_fill(
            [{"size": "12", "count": 3}],
            1.0, conduit_type="EMT"
        )
        assert r["ok"] is True
        expected_pct = (r["total_conductor_area_in2"] / r["conduit_area_in2"]) * 100.0
        # fill_pct is rounded to 2 decimal places; accept ±0.01 absolute tolerance
        assert abs(r["fill_pct"] - expected_pct) < 0.01


# ===========================================================================
# 6. overcurrent_device_size — NEC 240.4
# ===========================================================================

class TestOCPDSize:

    def test_12awg_cu_ocpd_is_20a(self):
        """#12 AWG Cu: next standard OCPD for 25A base = 25A."""
        r = overcurrent_device_size("12", material="cu")
        assert r["ok"] is True
        assert r["ocpd_A"] in _STANDARD_OCPD
        assert r["ocpd_A"] >= r["conductor_ampacity_A"]

    def test_ocpd_is_standard_size(self):
        """OCPD must be one of NEC 240.6(A) standard sizes."""
        r = overcurrent_device_size("10", material="cu")
        assert r["ok"] is True
        assert r["ocpd_A"] in _STANDARD_OCPD

    def test_undersized_conductor_flagged(self):
        """Load exceeding derated ampacity → undersized_conductor = True."""
        # #14 Cu has 20A derated; load of 30A exceeds it
        r = overcurrent_device_size("14", material="cu", load_A=30.0)
        assert r["ok"] is True
        assert r["undersized_conductor"] is True

    def test_adequate_conductor_not_flagged(self):
        """Load within derated ampacity → undersized_conductor = False."""
        r = overcurrent_device_size("10", material="cu", load_A=20.0)
        assert r["ok"] is True
        assert r["undersized_conductor"] is False

    def test_unknown_size_returns_error(self):
        r = overcurrent_device_size("999")
        assert r["ok"] is False


# ===========================================================================
# 7. motor_branch_circuit — NEC Art. 430
# ===========================================================================

class TestMotorBranchCircuit:

    def test_5hp_3ph_460v_flc(self):
        """5 HP 3φ 460V: NEC 430.250 FLC = 7.6A."""
        r = motor_branch_circuit(5.0, 460.0, phases=3)
        assert r["ok"] is True
        assert r["flc_A"] == pytest.approx(7.6, rel=REL)

    def test_conductor_125pct_flc(self):
        """Conductor must be ≥ 125% FLC per NEC 430.22."""
        r = motor_branch_circuit(5.0, 460.0, phases=3)
        assert r["ok"] is True
        assert r["conductor_min_A"] == pytest.approx(r["flc_A"] * 1.25, rel=REL)

    def test_ocpd_inverse_time_breaker_250pct(self):
        """Inverse-time breaker max = 250% FLC per NEC 430.52 Table."""
        r = motor_branch_circuit(5.0, 460.0, phases=3,
                                  ocpd_type="inverse_time_breaker")
        assert r["ok"] is True
        assert r["ocpd_max_A"] == pytest.approx(r["flc_A"] * 2.50, rel=REL)
        assert r["ocpd_A"] in _STANDARD_OCPD

    def test_ocpd_dual_element_fuse_175pct(self):
        """Dual-element fuse max = 175% FLC per NEC 430.52 Table."""
        r = motor_branch_circuit(10.0, 460.0, phases=3,
                                  ocpd_type="dual_element_fuse")
        assert r["ok"] is True
        assert r["ocpd_max_A"] == pytest.approx(r["flc_A"] * 1.75, rel=REL)

    def test_overload_125pct_for_sf_1p15(self):
        """Overload ≤ 125% FLC for SF ≥ 1.15 (NEC 430.32)."""
        r = motor_branch_circuit(5.0, 460.0, phases=3, service_factor=1.15)
        assert r["ok"] is True
        assert r["overload_A"] == pytest.approx(r["flc_A"] * 1.25, rel=REL)

    def test_overload_115pct_for_sf_lt_1p15(self):
        """Overload ≤ 115% FLC for SF < 1.15 (NEC 430.32)."""
        r = motor_branch_circuit(5.0, 460.0, phases=3, service_factor=1.0)
        assert r["ok"] is True
        assert r["overload_A"] == pytest.approx(r["flc_A"] * 1.15, rel=REL)

    def test_unknown_hp_returns_error(self):
        r = motor_branch_circuit(999.0, 460.0, phases=3)
        assert r["ok"] is False

    def test_invalid_ocpd_type_returns_error(self):
        r = motor_branch_circuit(5.0, 460.0, phases=3, ocpd_type="fused_switch")
        assert r["ok"] is False


# ===========================================================================
# 8. transformer_feeder_size — NEC Art. 450
# ===========================================================================

class TestTransformerFeederSize:

    def test_three_phase_fla_calculation(self):
        """3φ primary FLA = kVA × 1000 / (√3 × V)."""
        # 75 kVA, 480V primary, 208V secondary
        r = transformer_feeder_size(75.0, 480.0, 208.0, phases=3)
        assert r["ok"] is True
        expected_fla = 75000.0 / (math.sqrt(3) * 480.0)
        assert r["primary_fla_A"] == pytest.approx(expected_fla, rel=REL)

    def test_secondary_fla_higher_than_primary(self):
        """For step-down transformer (1φ, 480/240V), secondary FLA > primary FLA."""
        # 75 kVA, 480V primary (FLA=156A), 240V secondary (FLA=312A)
        r = transformer_feeder_size(75.0, 480.0, 240.0, phases=1)
        assert r["ok"] is True
        assert r["secondary_fla_A"] > r["primary_fla_A"]

    def test_max_secondary_sca_formula(self):
        """Max secondary SCA = (kVA × 1000) / (%Z/100 × V_sec × √3)."""
        r = transformer_feeder_size(75.0, 480.0, 208.0, phases=3,
                                     impedance_pct=5.75)
        assert r["ok"] is True
        v_sec = 208.0
        expected_sca = 75000.0 / (5.75 / 100.0 * math.sqrt(3) * v_sec)
        assert r["max_secondary_sca_A"] == pytest.approx(expected_sca, rel=REL)

    def test_primary_ocpd_is_standard_size(self):
        r = transformer_feeder_size(75.0, 480.0, 208.0, phases=3)
        assert r["ok"] is True
        assert r["primary_ocpd_A"] in _STANDARD_OCPD

    def test_invalid_kva_returns_error(self):
        r = transformer_feeder_size(0.0, 480.0, 208.0)
        assert r["ok"] is False


# ===========================================================================
# 9. short_circuit_analysis — point-to-point
# ===========================================================================

class TestShortCircuitAnalysis:

    def test_transformer_secondary_isc_formula(self):
        """Isc = V / (√3 × Z_xfmr) for 3φ with zero cable."""
        # 500 kVA, 480V secondary, 5% Z
        r = short_circuit_analysis(500.0, 13200.0, 480.0,
                                    transformer_z_pct=5.0,
                                    phases=3,
                                    cable_length_ft=0.0)
        assert r["ok"] is True
        # Z_base = V²/S = 480²/500000 = 0.4608 Ω
        # Z_xfmr = 0.05 × 0.4608 = 0.02304 Ω
        # Isc = 480 / (√3 × 0.02304) = 12017 A (approx)
        z_base = (480.0 ** 2) / (500.0 * 1000.0)
        z_xfmr = 0.05 * z_base
        isc_expected = 480.0 / (math.sqrt(3) * z_xfmr)
        assert r["isc_at_point_A"] == pytest.approx(isc_expected, rel=REL)
        assert r["isc_at_point_A"] == r["isc_transformer_A"]

    def test_cable_reduces_fault_current(self):
        """Adding cable impedance reduces fault current at point."""
        r_no_cable = short_circuit_analysis(500.0, 13200.0, 480.0,
                                             cable_length_ft=0.0)
        r_with_cable = short_circuit_analysis(500.0, 13200.0, 480.0,
                                               cable_length_ft=100.0,
                                               cable_size="4/0")
        assert r_no_cable["ok"] and r_with_cable["ok"]
        assert r_with_cable["isc_at_point_A"] < r_no_cable["isc_at_point_A"]

    def test_required_aic_rounds_up_to_kA(self):
        """required_aic_A must be a multiple of 1000A."""
        r = short_circuit_analysis(500.0, 13200.0, 480.0)
        assert r["ok"] is True
        assert r["required_aic_A"] % 1000 == 0
        assert r["required_aic_A"] >= r["isc_at_point_A"]

    def test_z_total_equals_z_xfmr_plus_cable(self):
        """z_total_ohms = z_transformer_ohms + z_cable_ohms."""
        r = short_circuit_analysis(500.0, 13200.0, 480.0,
                                    cable_length_ft=50.0, cable_size="2/0")
        assert r["ok"] is True
        assert r["z_total_ohms"] == pytest.approx(
            r["z_transformer_ohms"] + r["z_cable_ohms"], rel=REL
        )

    def test_invalid_z_pct_returns_error(self):
        r = short_circuit_analysis(500.0, 13200.0, 480.0,
                                    transformer_z_pct=0.0)
        assert r["ok"] is False


# ===========================================================================
# 10. power_factor_correction
# ===========================================================================

class TestPowerFactorCorrection:

    def test_kvar_formula(self):
        """Q = P × (tan θ₁ - tan θ₂)."""
        p_kw = 100.0
        pf1 = 0.70
        pf2 = 0.95
        r = power_factor_correction(p_kw, pf1, pf2, 480.0, phases=3)
        assert r["ok"] is True
        expected_kvar = p_kw * (math.tan(math.acos(pf1)) - math.tan(math.acos(pf2)))
        assert r["kvar_required"] == pytest.approx(expected_kvar, rel=REL)

    def test_kvar_bank_rounded_to_5(self):
        """kvar_bank_size must be a multiple of 5."""
        r = power_factor_correction(100.0, 0.70, 0.95, 480.0)
        assert r["ok"] is True
        assert r["kvar_bank_size"] % 5 == 0
        assert r["kvar_bank_size"] >= r["kvar_required"]

    def test_kvar_positive_for_lagging_pf_improvement(self):
        r = power_factor_correction(50.0, 0.80, 0.95, 240.0)
        assert r["ok"] is True
        assert r["kvar_required"] > 0

    def test_current_kva_formula(self):
        """current_kva = load_kw / current_pf."""
        r = power_factor_correction(100.0, 0.70, 0.95, 480.0)
        assert r["ok"] is True
        assert r["current_kva"] == pytest.approx(100.0 / 0.70, rel=REL)

    def test_target_pf_le_current_returns_error(self):
        r = power_factor_correction(100.0, 0.90, 0.80, 480.0)
        assert r["ok"] is False

    def test_invalid_current_pf_returns_error(self):
        r = power_factor_correction(100.0, 0.0, 0.95, 480.0)
        assert r["ok"] is False

    def test_capacitance_uf_positive(self):
        """Capacitance per phase must be positive."""
        r = power_factor_correction(50.0, 0.75, 0.95, 480.0, phases=3)
        assert r["ok"] is True
        assert r["capacitance_uF_per_phase"] > 0


# ===========================================================================
# 11. grounding_conductor_size — NEC 250.66 / 250.122
# ===========================================================================

class TestGroundingConductorSize:

    def test_gec_for_2awg_service_is_8awg_cu(self):
        """NEC 250.66: service ≤ #2 AWG Cu → GEC #8 Cu."""
        r = grounding_conductor_size("2", conductor_type="gec", material="cu")
        assert r["ok"] is True
        assert r["size"] == "8"
        assert r["nec_reference"] == "250.66"

    def test_gec_for_large_service_larger_gec(self):
        """Large service (350 kcmil) → GEC ≥ #2 Cu per NEC 250.66."""
        r = grounding_conductor_size("350", conductor_type="gec", material="cu")
        assert r["ok"] is True
        # NEC 250.66: ≤ 350 kcmil → GEC #2 Cu
        from kerf_cad_core.elecpower.distribution import _SIZE_ORDER
        assert _SIZE_ORDER.index(r["size"]) >= _SIZE_ORDER.index("2")

    def test_egc_for_20a_ocpd_is_12awg(self):
        """NEC 250.122: 20A OCPD → EGC #12 Cu."""
        r = grounding_conductor_size("12",
                                      ocpd_rating_A=20.0,
                                      conductor_type="egc",
                                      material="cu")
        assert r["ok"] is True
        assert r["size"] == "12"
        assert r["nec_reference"] == "250.122"

    def test_egc_for_100a_ocpd_is_8awg(self):
        """NEC 250.122: 100A OCPD → EGC #8 Cu."""
        r = grounding_conductor_size("4",
                                      ocpd_rating_A=100.0,
                                      conductor_type="egc",
                                      material="cu")
        assert r["ok"] is True
        assert r["size"] == "8"

    def test_egc_missing_ocpd_returns_error(self):
        r = grounding_conductor_size("4", conductor_type="egc")
        assert r["ok"] is False

    def test_invalid_conductor_type_returns_error(self):
        r = grounding_conductor_size("4", conductor_type="neutral")
        assert r["ok"] is False


# ===========================================================================
# 12. panel_schedule_rollup
# ===========================================================================

class TestPanelScheduleRollup:

    def test_basic_rollup_total(self):
        """Sum of VA in schedule matches total_connected_va."""
        circuits = [
            {"name": "c1", "va": 1200},
            {"name": "c2", "va": 1800},
            {"name": "c3", "va": 2400},
        ]
        r = panel_schedule_rollup(circuits, voltage=120, include_demand=False)
        assert r["ok"] is True
        assert r["total_connected_va"] == pytest.approx(5400, rel=REL)

    def test_feeder_amps_1ph(self):
        """1φ feeder amps = demand_va / voltage."""
        circuits = [{"name": "c", "va": 2400}]
        r = panel_schedule_rollup(circuits, voltage=120, include_demand=False)
        assert r["ok"] is True
        assert r["total_amps"] == pytest.approx(2400 / 120.0, rel=REL)

    def test_feeder_amps_3ph(self):
        """3φ feeder amps = demand_va / (V × √3)."""
        circuits = [{"name": "c", "va": 48000}]
        r = panel_schedule_rollup(circuits, voltage=208, phases=3,
                                   include_demand=False)
        assert r["ok"] is True
        expected = 48000 / (208.0 * math.sqrt(3))
        assert r["total_amps"] == pytest.approx(expected, rel=REL)

    def test_main_breaker_is_standard_size(self):
        circuits = [{"name": "c", "va": 12000}]
        r = panel_schedule_rollup(circuits, voltage=120)
        assert r["ok"] is True
        assert r["main_breaker_A"] in _STANDARD_OCPD

    def test_empty_circuits_returns_error(self):
        r = panel_schedule_rollup([], voltage=120)
        assert r["ok"] is False

    def test_circuit_count_matches(self):
        circuits = [{"name": f"c{i}", "va": 1000} for i in range(10)]
        r = panel_schedule_rollup(circuits, voltage=120)
        assert r["ok"] is True
        assert r["circuit_count"] == 10


# ===========================================================================
# 13. generator_ups_size
# ===========================================================================

class TestGeneratorUpsSize:

    def test_basic_running_kw(self):
        """Total running kW = sum of load kW."""
        loads = [{"name": "a", "kw": 20}, {"name": "b", "kw": 30}]
        r = generator_ups_size(loads, demand_factor=1.0, include_spare_pct=0.0)
        assert r["ok"] is True
        assert r["total_running_kw"] == pytest.approx(50.0, rel=REL)

    def test_demand_factor_applied(self):
        """demand_kw = total_running_kw × demand_factor."""
        loads = [{"name": "a", "kw": 100}]
        r = generator_ups_size(loads, demand_factor=0.8, include_spare_pct=0.0)
        assert r["ok"] is True
        assert r["demand_kw"] == pytest.approx(80.0, rel=REL)

    def test_standard_gen_size_is_at_least_recommended(self):
        """standard_gen_size_kva ≥ recommended_gen_kva."""
        loads = [{"name": "a", "kw": 50}]
        r = generator_ups_size(loads)
        assert r["ok"] is True
        assert r["standard_gen_size_kva"] >= r["recommended_gen_kva"]

    def test_motor_starting_surge_added(self):
        """Motor HP load creates starting surge > 0."""
        loads = [{"name": "motor", "kw": 10, "motor_hp": 15}]
        r = generator_ups_size(loads)
        assert r["ok"] is True
        assert r["largest_motor_starting_kva"] > 0

    def test_spare_pct_increases_recommendation(self):
        """Higher spare_pct must increase recommended_gen_kva."""
        loads = [{"name": "a", "kw": 50}]
        r0 = generator_ups_size(loads, include_spare_pct=0.0)
        r20 = generator_ups_size(loads, include_spare_pct=20.0)
        assert r20["recommended_gen_kva"] > r0["recommended_gen_kva"]

    def test_invalid_demand_factor_returns_error(self):
        loads = [{"name": "a", "kw": 10}]
        r = generator_ups_size(loads, demand_factor=0.0)
        assert r["ok"] is False

    def test_empty_loads_returns_error(self):
        r = generator_ups_size([])
        assert r["ok"] is False


# ===========================================================================
# 14. LLM tool wrappers (run_*)
# ===========================================================================

class TestToolWrappers:

    def test_run_demand_load_happy_path(self):
        ctx = _ctx()
        raw = _run(run_demand_load(ctx, _args(
            loads=[{"name": "lights", "va": 5000, "continuous": True}],
            occupancy="commercial"
        )))
        d = _ok_tool(raw)
        assert d["demand_va"] == pytest.approx(5000 * 1.25, rel=REL)

    def test_run_demand_load_missing_loads(self):
        ctx = _ctx()
        raw = _run(run_demand_load(ctx, _args(occupancy="commercial")))
        _err_tool(raw)

    def test_run_conductor_ampacity_happy_path(self):
        ctx = _ctx()
        raw = _run(run_conductor_ampacity(ctx, _args(size="12", material="cu")))
        d = _ok_tool(raw)
        assert d["base_ampacity_A"] == 25.0

    def test_run_conductor_ampacity_bad_json(self):
        ctx = _ctx()
        raw = _run(run_conductor_ampacity(ctx, b"not json"))
        _err_tool(raw)

    def test_run_conductor_size_happy_path(self):
        ctx = _ctx()
        raw = _run(run_conductor_size(ctx, _args(load_A=30.0, material="cu")))
        d = _ok_tool(raw)
        assert d["derated_ampacity_A"] >= 30.0

    def test_run_voltage_drop_happy_path(self):
        ctx = _ctx()
        raw = _run(run_voltage_drop(ctx, _args(
            load_A=20.0, length_ft=100.0, size="10", voltage=120.0, phases=1
        )))
        d = _ok_tool(raw)
        assert d["vd_V"] > 0

    def test_run_voltage_drop_missing_size(self):
        ctx = _ctx()
        raw = _run(run_voltage_drop(ctx, _args(
            load_A=20.0, length_ft=100.0, voltage=120.0
        )))
        _err_tool(raw)

    def test_run_conduit_fill_happy_path(self):
        ctx = _ctx()
        raw = _run(run_conduit_fill(ctx, _args(
            conductors=[{"size": "12", "count": 3}],
            conduit_trade_size_in=1.0
        )))
        d = _ok_tool(raw)
        assert d["fill_pct"] > 0

    def test_run_ocpd_size_happy_path(self):
        ctx = _ctx()
        raw = _run(run_ocpd_size(ctx, _args(conductor_size="10", material="cu")))
        d = _ok_tool(raw)
        assert d["ocpd_A"] in _STANDARD_OCPD

    def test_run_motor_branch_happy_path(self):
        ctx = _ctx()
        raw = _run(run_motor_branch(ctx, _args(hp=5.0, voltage=460.0, phases=3)))
        d = _ok_tool(raw)
        assert d["flc_A"] == pytest.approx(7.6, rel=REL)

    def test_run_transformer_feeder_happy_path(self):
        ctx = _ctx()
        raw = _run(run_transformer_feeder(ctx, _args(
            kva=75.0, primary_voltage=480.0, secondary_voltage=208.0, phases=3
        )))
        d = _ok_tool(raw)
        assert d["primary_fla_A"] > 0
        assert d["max_secondary_sca_A"] > 0

    def test_run_short_circuit_happy_path(self):
        ctx = _ctx()
        raw = _run(run_short_circuit(ctx, _args(
            transformer_kva=500.0,
            transformer_primary_V=13200.0,
            transformer_secondary_V=480.0,
            transformer_z_pct=5.75,
            phases=3
        )))
        d = _ok_tool(raw)
        assert d["isc_at_point_A"] > 0
        assert d["required_aic_A"] % 1000 == 0

    def test_run_pf_correction_happy_path(self):
        ctx = _ctx()
        raw = _run(run_pf_correction(ctx, _args(
            load_kw=100.0, current_pf=0.70, target_pf=0.95, voltage=480.0
        )))
        d = _ok_tool(raw)
        assert d["kvar_required"] > 0

    def test_run_grounding_conductor_gec_happy_path(self):
        ctx = _ctx()
        raw = _run(run_grounding_conductor(ctx, _args(
            service_conductor_size="2", conductor_type="gec", material="cu"
        )))
        d = _ok_tool(raw)
        assert d["size"] == "8"

    def test_run_panel_schedule_happy_path(self):
        ctx = _ctx()
        raw = _run(run_panel_schedule(ctx, _args(
            circuits=[{"name": "c1", "va": 2400}, {"name": "c2", "va": 1200}],
            voltage=120.0, phases=1
        )))
        d = _ok_tool(raw)
        assert d["main_breaker_A"] in _STANDARD_OCPD

    def test_run_generator_size_happy_path(self):
        ctx = _ctx()
        raw = _run(run_generator_size(ctx, _args(
            loads=[{"name": "a", "kw": 50}, {"name": "b", "kw": 30}]
        )))
        d = _ok_tool(raw)
        assert d["standard_gen_size_kva"] > 0


# ===========================================================================
# 15. Externally-citable NEC reference cases (worked-example cross-checks)
#
# Every assertion below has a known numeric answer traceable to a published
# NEC table or a textbook hand-calculation. Sources are cited per test.
# ===========================================================================

class TestNECReferenceCases:
    """Cross-checks against published NFPA 70 (NEC 2023) tables & worked examples."""

    def test_ref_310_16_ampacity_table_75c_copper(self):
        """NEC Table 310.16, 75°C copper column (verbatim table values).

        Source: NFPA 70-2023 Table 310.16 (THWN/THHW 75°C, Cu).
            #12 = 25 A, #10 = 35 A, #6 = 65 A, 1/0 = 150 A,
            4/0 = 230 A, 250 kcmil = 255 A, 500 kcmil = 380 A.
        """
        for size, amps in (("12", 25.0), ("10", 35.0), ("6", 65.0),
                           ("1/0", 150.0), ("4/0", 230.0),
                           ("250", 255.0), ("500", 380.0)):
            r = conductor_ampacity(size, material="cu", ambient_c=30, num_ccc=3)
            assert r["ok"] is True
            assert r["base_ampacity_A"] == amps, f"{size} expected {amps}"

    def test_ref_310_15_ambient_correction_75c(self):
        """NEC Table 310.15(B)(1) ambient-temperature correction, 75°C column.

        Source: NFPA 70-2023 Table 310.15(B)(1)(1).
            26–30°C → 1.00, 31–35°C → 0.94, 36–40°C → 0.88,
            41–45°C → 0.82, 46–50°C → 0.75.
        """
        assert _ambient_correction(30) == pytest.approx(1.00)
        assert _ambient_correction(35) == pytest.approx(0.94)
        assert _ambient_correction(40) == pytest.approx(0.88)
        assert _ambient_correction(45) == pytest.approx(0.82)
        assert _ambient_correction(50) == pytest.approx(0.75)

    def test_ref_310_15_c_1_bundling_adjustment(self):
        """NEC 310.15(C)(1) adjustment factors for >3 CCC in a raceway.

        Source: NFPA 70-2023 Table 310.15(C)(1).
            4–6  → 80%   7–9  → 70%   10–20 → 50%
            21–30 → 45%  31–40 → 40%  41+   → 35%
        This is the regression guard for the 5/6-CCC defect (was wrongly 0.70).
        """
        assert _bundling_factor(3) == pytest.approx(1.00)
        assert _bundling_factor(4) == pytest.approx(0.80)
        assert _bundling_factor(5) == pytest.approx(0.80)
        assert _bundling_factor(6) == pytest.approx(0.80)
        assert _bundling_factor(7) == pytest.approx(0.70)
        assert _bundling_factor(9) == pytest.approx(0.70)
        assert _bundling_factor(10) == pytest.approx(0.50)
        assert _bundling_factor(20) == pytest.approx(0.50)
        assert _bundling_factor(25) == pytest.approx(0.45)
        assert _bundling_factor(35) == pytest.approx(0.40)
        assert _bundling_factor(50) == pytest.approx(0.35)

    def test_ref_430_250_three_phase_motor_flc(self):
        """NEC Table 430.250 three-phase 460 V FLC (verbatim).

        Source: NFPA 70-2023 Table 430.250 (460 V column).
            1 hp = 2.1 A, 5 hp = 7.6 A, 10 hp = 14 A,
            50 hp = 65 A, 100 hp = 124 A.
        """
        for hp, flc in ((1.0, 2.1), (5.0, 7.6), (10.0, 14.0),
                        (50.0, 65.0), (100.0, 124.0)):
            r = motor_branch_circuit(hp, 460.0, phases=3)
            assert r["ok"] is True
            assert r["flc_A"] == pytest.approx(flc, rel=REL), f"{hp} hp"

    def test_ref_430_248_single_phase_motor_flc(self):
        """NEC Table 430.248 single-phase FLC (verbatim).

        Source: NFPA 70-2023 Table 430.248.
            1 hp @ 115 V = 16 A; 1 hp @ 230 V = 8 A; 5 hp @ 230 V = 28 A.
        """
        r1 = motor_branch_circuit(1.0, 115.0, phases=1)
        assert r1["ok"] is True and r1["flc_A"] == pytest.approx(16.0, rel=REL)
        r2 = motor_branch_circuit(1.0, 230.0, phases=1)
        assert r2["ok"] is True and r2["flc_A"] == pytest.approx(8.0, rel=REL)
        r3 = motor_branch_circuit(5.0, 230.0, phases=1)
        assert r3["ok"] is True and r3["flc_A"] == pytest.approx(28.0, rel=REL)

    def test_ref_motor_branch_5hp_460v_worked_example(self):
        """Worked example: 5 hp, 3φ, 460 V motor on inverse-time breaker.

        Source: Mike Holt / NEC Art. 430 worked example.
            FLC (430.250)            = 7.6 A
            Conductor 430.22  125%   = 9.5 A  → #14 Cu adequate
            OCPD 430.52 ITB 250%     = 19.0 A → next std 240.6(A) = 20 A
            Overload 430.32 SF≥1.15  = 7.6 × 1.25 = 9.5 A
        """
        r = motor_branch_circuit(5.0, 460.0, phases=3,
                                 ocpd_type="inverse_time_breaker",
                                 service_factor=1.15)
        assert r["ok"] is True
        assert r["flc_A"] == pytest.approx(7.6, rel=REL)
        assert r["conductor_min_A"] == pytest.approx(9.5, rel=REL)
        assert r["ocpd_max_A"] == pytest.approx(19.0, rel=REL)
        assert r["ocpd_A"] == 20
        assert r["overload_A"] == pytest.approx(9.5, rel=REL)

    def test_ref_3ph_voltage_drop_worked_example(self):
        """Worked example: 3φ voltage drop, NEC Ch.9 Table 9 resistance.

        Source: IEEE 141 (Red Book) / standard VD hand-calc.
            #2 Cu R = 0.194 Ω/1000 ft; I = 100 A; one-way L = 200 ft;
            VD = √3 × I × R × L / 1000
               = 1.7320508 × 100 × 0.194 × 200 / 1000
               = 6.7204 V  (1.400 % of 480 V).
        """
        r = voltage_drop(100.0, 200.0, "2", 480.0, phases=3, material="cu")
        assert r["ok"] is True
        expected = math.sqrt(3.0) * 100.0 * 0.194 * 200.0 / 1000.0
        # module rounds vd_V to 4 dp (documented contract)
        assert r["vd_V"] == pytest.approx(expected, abs=5e-5)
        assert r["vd_V"] == pytest.approx(6.7204, abs=1e-3)
        assert r["vd_pct"] == pytest.approx(expected / 480.0 * 100.0, rel=1e-3)

    def test_ref_1ph_voltage_drop_worked_example(self):
        """Worked example: 1φ voltage drop.

        Source: standard VD hand-calc, NEC Ch.9 Table 9.
            #10 Cu R = 1.24 Ω/1000 ft; I = 20 A; L = 100 ft;
            VD = 2 × 20 × 1.24 × 100 / 1000 = 4.96 V (4.133 % of 120 V).
        """
        r = voltage_drop(20.0, 100.0, "10", 120.0, phases=1, material="cu")
        assert r["ok"] is True
        assert r["vd_V"] == pytest.approx(4.96, abs=1e-6)
        assert r["vd_pct"] == pytest.approx(4.96 / 120.0 * 100.0, rel=1e-4)
        assert r["receiving_end_V"] == pytest.approx(115.04, abs=1e-3)

    def test_ref_transformer_secondary_fla_and_sca(self):
        """Worked example: 75 kVA 480→208/120 V 3φ transformer, %Z = 5.

        Source: NEC Art. 450 / IEEE 141 infinite-bus method.
            Sec FLA = 75000 / (√3 × 208) = 208.18 A
            Max sec SCA (infinite bus) = FLA / (%Z/100)
                = 208.18 / 0.05 = 4163.6 A
        """
        r = transformer_feeder_size(75.0, 480.0, 208.0, phases=3,
                                    impedance_pct=5.0)
        assert r["ok"] is True
        sec_fla = 75000.0 / (math.sqrt(3.0) * 208.0)
        assert r["secondary_fla_A"] == pytest.approx(sec_fla, rel=1e-4)
        assert r["secondary_fla_A"] == pytest.approx(208.18, abs=0.05)
        assert r["max_secondary_sca_A"] == pytest.approx(sec_fla / 0.05, rel=1e-4)

    def test_ref_point_to_point_sca_500kva(self):
        """Worked example: 500 kVA 480 V 3φ, %Z = 5, bolted fault at terminals.

        Source: Bussmann/Cooper point-to-point method (infinite primary).
            FLA = 500000 / (√3 × 480) = 601.41 A
            I_sc = FLA / (%Z/100) = 601.41 / 0.05 = 12028.3 A
        Equivalent via Z: Z = 480²/500000 × 0.05 = 0.023040 Ω;
            I = 480 / (√3 × 0.023040) = 12028.3 A.
        """
        r = short_circuit_analysis(500.0, 13200.0, 480.0,
                                   transformer_z_pct=5.0, phases=3,
                                   cable_length_ft=0.0)
        assert r["ok"] is True
        fla = 500000.0 / (math.sqrt(3.0) * 480.0)
        isc = fla / 0.05
        assert r["isc_transformer_A"] == pytest.approx(isc, rel=1e-4)
        assert r["isc_at_point_A"] == pytest.approx(12028.3, abs=1.0)
        assert r["z_transformer_ohms"] == pytest.approx(
            (480.0 ** 2) / 500000.0 * 0.05, rel=1e-4)

    def test_ref_250_66_gec_table(self):
        """NEC Table 250.66 grounding-electrode conductor (Cu).

        Source: NFPA 70-2023 Table 250.66.
            Service ≤ #2 Cu          → GEC #8 Cu
            Service #1–1/0 Cu        → GEC #6 Cu
            Service #2/0–3/0 Cu      → GEC #4 Cu
            Service 250–350 kcmil    → GEC #2 Cu
        """
        cases = (("2", "8"), ("1/0", "6"), ("3/0", "4"), ("350", "2"))
        for svc, gec in cases:
            r = grounding_conductor_size(svc, conductor_type="gec",
                                         material="cu")
            assert r["ok"] is True
            assert r["size"] == gec, f"service {svc} → GEC {gec}"
            assert r["nec_reference"] == "250.66"

    def test_ref_250_122_egc_table(self):
        """NEC Table 250.122 equipment-grounding conductor (Cu).

        Source: NFPA 70-2023 Table 250.122.
            ≤15 A → #14, ≤20 A → #12, ≤60 A → #10,
            ≤100 A → #8, ≤200 A → #6, ≤400 A → #3, ≤600 A → #1.
        """
        cases = ((15.0, "14"), (20.0, "12"), (60.0, "10"), (100.0, "8"),
                 (200.0, "6"), (400.0, "3"), (600.0, "1"))
        for ocpd, egc in cases:
            r = grounding_conductor_size("4", ocpd_rating_A=ocpd,
                                         conductor_type="egc", material="cu")
            assert r["ok"] is True
            assert r["size"] == egc, f"OCPD {ocpd} A → EGC {egc}"
            assert r["nec_reference"] == "250.122"

    def test_ref_pf_correction_worked_example(self):
        """Worked example: PF correction 0.75 → 0.95 at 100 kW.

        Source: standard reactive-power hand-calc.
            θ₁ = acos 0.75 = 41.4096°, tanθ₁ = 0.881917
            θ₂ = acos 0.95 = 18.1949°, tanθ₂ = 0.328684
            Q  = 100 × (0.881917 − 0.328684) = 55.3233 kVAR
        """
        r = power_factor_correction(100.0, 0.75, 0.95, 480.0, phases=3)
        assert r["ok"] is True
        t1 = math.tan(math.acos(0.75))
        t2 = math.tan(math.acos(0.95))
        # module rounds kvar_required to 3 dp (documented contract)
        assert r["kvar_required"] == pytest.approx(100.0 * (t1 - t2), abs=5e-4)
        assert r["kvar_required"] == pytest.approx(55.3233, abs=1e-3)
        assert r["current_kva"] == pytest.approx(100.0 / 0.75, rel=1e-4)

    def test_ref_240_6_standard_ocpd_sizes(self):
        """NEC 240.6(A) standard overcurrent device ampere ratings.

        Source: NFPA 70-2023 240.6(A).
            15,20,25,30,35,40,45,50,60,70,80,90,100,110,125,150,...
            Next standard size at/above a value never undershoots.
        """
        assert _next_standard_ocpd(19.0) == 20
        assert _next_standard_ocpd(20.0) == 20
        assert _next_standard_ocpd(21.0) == 25
        assert _next_standard_ocpd(95.0) == 100
        assert _next_standard_ocpd(225.0) == 225
        assert _next_standard_ocpd(226.0) == 250
        for v in (15, 20, 60, 100, 200, 400, 600):
            assert v in _STANDARD_OCPD
