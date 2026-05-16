"""
Hermetic tests for kerf_cad_core.fluidpower — hydraulic fluid-power circuit sizing.

Coverage:
  circuit.cylinder              — force, velocity, regeneration
  circuit.pump                  — flow, power, torque
  circuit.motor                 — torque, speed, flow
  circuit.accumulator           — isothermal & adiabatic, pre-charge check
  circuit.valve_cv              — Cv and Kv formulas
  circuit.line_pressure_drop    — laminar (H-P) and turbulent (D-W/Colebrook)
  circuit.line_size             — velocity-limit bore selection
  circuit.reservoir             — rule-of-thumb volume
  circuit.thermal_balance       — heat load and balance check
  tools.*                       — LLM tool wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network.
Formulas verified algebraically against published expressions.

References
----------
Vickers Industrial Hydraulics Manual (4th ed.)
Parker Hannifin Hydraulic Systems Design Guide
ISO 4399 — Hydraulic fluid power

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.fluidpower.circuit import (
    cylinder,
    pump,
    motor,
    accumulator,
    valve_cv,
    line_pressure_drop,
    line_size,
    reservoir,
    thermal_balance,
)
from kerf_cad_core.fluidpower.tools import (
    run_fp_cylinder,
    run_fp_pump,
    run_fp_motor,
    run_fp_accumulator,
    run_fp_valve_cv,
    run_fp_line_pressure_drop,
    run_fp_line_size,
    run_fp_reservoir,
    run_fp_thermal_balance,
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


REL = 1e-9   # relative tolerance for floating-point comparisons


# ===========================================================================
# 1. cylinder
# ===========================================================================

class TestCylinder:

    def test_extend_force_formula(self):
        """F_extend = pressure × A_bore = P × π/4 × bore²."""
        bore, rod, P, Q = 0.08, 0.04, 10e6, 1e-3
        res = cylinder(bore, rod, P, Q)
        assert res["ok"] is True
        A_bore = math.pi / 4.0 * bore ** 2
        assert abs(res["F_extend_N"] - P * A_bore) / (P * A_bore) < REL

    def test_retract_force_formula(self):
        """F_retract = pressure × A_rod = P × π/4 × (bore² − rod²)."""
        bore, rod, P, Q = 0.10, 0.05, 8e6, 2e-3
        res = cylinder(bore, rod, P, Q)
        assert res["ok"] is True
        A_rod = math.pi / 4.0 * (bore ** 2 - rod ** 2)
        assert abs(res["F_retract_N"] - P * A_rod) / (P * A_rod) < REL

    def test_extend_velocity_formula(self):
        """v_extend = Q / A_bore."""
        bore, rod, P, Q = 0.06, 0.03, 5e6, 5e-4
        res = cylinder(bore, rod, P, Q)
        A_bore = math.pi / 4.0 * bore ** 2
        assert abs(res["v_extend_ms"] - Q / A_bore) / (Q / A_bore) < REL

    def test_retract_velocity_greater_than_extend(self):
        """Retract velocity > extend velocity because A_rod < A_bore."""
        res = cylinder(0.10, 0.06, 10e6, 1e-3)
        assert res["v_retract_ms"] > res["v_extend_ms"]

    def test_extend_force_greater_than_retract(self):
        """Extend force > retract force (full bore vs annulus)."""
        res = cylinder(0.08, 0.04, 10e6, 1e-3)
        assert res["F_extend_N"] > res["F_retract_N"]

    def test_regen_velocity_greater_than_extend(self):
        """In regen mode, effective area = rod annulus → faster extend."""
        # bore=100mm, rod=60mm → A_regen = π/4 × 0.06² which is ~smaller than A_bore
        # v_regen = Q / A_regen > Q / A_bore = v_extend
        res = cylinder(0.10, 0.06, 10e6, 2e-3, regen=True)
        assert res["ok"] is True
        assert res["v_regen_ms"] > res["v_extend_ms"]

    def test_area_fields_correct(self):
        """A_bore and A_rod fields match analytical values."""
        bore, rod = 0.12, 0.07
        res = cylinder(bore, rod, 5e6, 1e-3)
        assert abs(res["A_bore_m2"] - math.pi / 4 * bore ** 2) < 1e-15
        assert abs(res["A_rod_m2"]  - math.pi / 4 * (bore ** 2 - rod ** 2)) < 1e-15

    def test_rod_equals_bore_returns_error(self):
        """rod_m == bore_m must return ok=False."""
        res = cylinder(0.10, 0.10, 5e6, 1e-3)
        assert res["ok"] is False

    def test_rod_larger_than_bore_returns_error(self):
        res = cylinder(0.05, 0.10, 5e6, 1e-3)
        assert res["ok"] is False

    def test_negative_bore_returns_error(self):
        res = cylinder(-0.1, 0.05, 5e6, 1e-3)
        assert res["ok"] is False

    def test_zero_pressure_returns_error(self):
        res = cylinder(0.10, 0.05, 0.0, 1e-3)
        assert res["ok"] is False


# ===========================================================================
# 2. pump
# ===========================================================================

class TestPump:

    def test_actual_flow_formula(self):
        """Q_actual = displacement × (rpm/60) × vol_eff."""
        D, n, ev, eta, P = 16e-6, 1500.0, 0.92, 0.85, 20e6
        res = pump(D, n, ev, eta, P)
        assert res["ok"] is True
        Q_expected = D * (n / 60.0) * ev
        assert abs(res["Q_actual_m3s"] - Q_expected) / Q_expected < REL

    def test_theoretical_flow_formula(self):
        """Q_theoretical = displacement × (rpm/60)."""
        D, n, ev, eta, P = 20e-6, 1000.0, 0.95, 0.88, 15e6
        res = pump(D, n, ev, eta, P)
        Q_th = D * (n / 60.0)
        assert abs(res["Q_theoretical_m3s"] - Q_th) / Q_th < REL

    def test_input_power_formula(self):
        """P_input = P_supply × Q_actual / overall_eff."""
        D, n, ev, eta, P = 25e-6, 1200.0, 0.90, 0.82, 25e6
        res = pump(D, n, ev, eta, P)
        Q_actual = D * (n / 60.0) * ev
        P_input_expected = P * Q_actual / eta
        assert abs(res["P_input_W"] - P_input_expected) / P_input_expected < REL

    def test_hydraulic_power_formula(self):
        """P_hydraulic = P_supply × Q_actual."""
        D, n, ev, eta, P = 10e-6, 1800.0, 0.93, 0.87, 18e6
        res = pump(D, n, ev, eta, P)
        Q_actual = D * (n / 60.0) * ev
        P_hyd = P * Q_actual
        assert abs(res["P_hydraulic_W"] - P_hyd) / P_hyd < REL

    def test_input_power_greater_than_hydraulic(self):
        """P_input >= P_hydraulic (losses exist)."""
        res = pump(20e-6, 1500.0, 0.92, 0.85, 20e6)
        assert res["P_input_W"] >= res["P_hydraulic_W"]

    def test_torque_formula(self):
        """T_input = D × P / (2π × η_m), η_m = η_overall / η_v."""
        D, n, ev, eta, P = 30e-6, 1000.0, 0.90, 0.85, 15e6
        res = pump(D, n, ev, eta, P)
        eta_m = eta / ev
        T_expected = D * P / (2.0 * math.pi * eta_m)
        assert abs(res["T_input_Nm"] - T_expected) / T_expected < REL

    def test_efficiency_unity_is_accepted(self):
        """vol_eff = overall_eff = 1.0 is valid (ideal pump)."""
        res = pump(10e-6, 1000.0, 1.0, 1.0, 5e6)
        assert res["ok"] is True

    def test_zero_displacement_returns_error(self):
        res = pump(0.0, 1500.0, 0.92, 0.85, 20e6)
        assert res["ok"] is False

    def test_efficiency_above_one_returns_error(self):
        res = pump(20e-6, 1500.0, 1.1, 0.85, 20e6)
        assert res["ok"] is False

    def test_zero_rpm_returns_error(self):
        res = pump(20e-6, 0.0, 0.92, 0.85, 20e6)
        assert res["ok"] is False


# ===========================================================================
# 3. motor
# ===========================================================================

class TestMotor:

    def test_theoretical_torque_formula(self):
        """T_theoretical = D × ΔP / (2π)."""
        D, P, n = 50e-6, 15e6, 1000.0
        res = motor(D, P, n)
        assert res["ok"] is True
        T_th = D * P / (2.0 * math.pi)
        assert abs(res["T_theoretical_Nm"] - T_th) / T_th < REL

    def test_output_torque_less_than_theoretical(self):
        """T_output = T_theoretical × η_m < T_theoretical (η_m < 1)."""
        res = motor(50e-6, 15e6, 1000.0, mech_eff=0.90)
        assert res["T_output_Nm"] < res["T_theoretical_Nm"]
        ratio = res["T_output_Nm"] / res["T_theoretical_Nm"]
        assert abs(ratio - 0.90) < REL

    def test_flow_consumed_formula(self):
        """Q_actual = D × (rpm/60) / vol_eff."""
        D, P, n, ev = 40e-6, 10e6, 800.0, 0.93
        res = motor(D, P, n, vol_eff=ev)
        Q_actual = D * (n / 60.0) / ev
        assert abs(res["Q_actual_m3s"] - Q_actual) / Q_actual < REL

    def test_output_power_formula(self):
        """P_output = T_output × ω = T_output × 2π × (rpm/60)."""
        D, P, n = 60e-6, 20e6, 1200.0
        res = motor(D, P, n)
        omega = 2.0 * math.pi * (n / 60.0)
        P_out = res["T_output_Nm"] * omega
        assert abs(res["P_output_W"] - P_out) / P_out < REL

    def test_angular_velocity_formula(self):
        """omega_rad_s = 2π × rpm/60."""
        res = motor(30e-6, 8e6, 1500.0)
        assert abs(res["omega_rad_s"] - 2.0 * math.pi * 1500.0 / 60.0) < REL

    def test_negative_displacement_returns_error(self):
        res = motor(-10e-6, 5e6, 1000.0)
        assert res["ok"] is False

    def test_zero_pressure_returns_error(self):
        res = motor(30e-6, 0.0, 1000.0)
        assert res["ok"] is False

    def test_mech_eff_above_one_returns_error(self):
        res = motor(30e-6, 5e6, 1000.0, mech_eff=1.05)
        assert res["ok"] is False


# ===========================================================================
# 4. accumulator
# ===========================================================================

class TestAccumulator:

    def test_isothermal_delta_V(self):
        """Boyle's law: ΔV = V × [(P1/P2) − (P1/P3)]  (n=1 isothermal)."""
        V, P1, P2, P3 = 0.010, 70e5, 100e5, 160e5
        res = accumulator(V, P1, P2, P3, process="isothermal")
        assert res["ok"] is True
        dV_expected = V * ((P1 / P2) ** 1.0 - (P1 / P3) ** 1.0)
        assert abs(res["delta_V_m3"] - dV_expected) / abs(dV_expected) < REL

    def test_adiabatic_delta_V(self):
        """Adiabatic: ΔV = V × [(P1/P2)^(1/1.4) − (P1/P3)^(1/1.4)]."""
        V, P1, P2, P3 = 0.020, 80e5, 120e5, 200e5
        res = accumulator(V, P1, P2, P3, process="adiabatic")
        assert res["ok"] is True
        n = 1.4
        dV_expected = V * ((P1 / P2) ** (1.0 / n) - (P1 / P3) ** (1.0 / n))
        assert abs(res["delta_V_m3"] - dV_expected) / abs(dV_expected) < REL

    def test_adiabatic_less_usable_than_isothermal(self):
        """Adiabatic process yields less usable volume than isothermal."""
        V, P1, P2, P3 = 0.010, 80e5, 120e5, 200e5
        dV_iso = accumulator(V, P1, P2, P3, process="isothermal")["delta_V_m3"]
        dV_adi = accumulator(V, P1, P2, P3, process="adiabatic")["delta_V_m3"]
        assert dV_iso > dV_adi

    def test_precharge_ratio_flagged_when_too_high(self):
        """P1 > 0.90 × P2 must set precharge_ok=False and add warning."""
        V, P1, P2, P3 = 0.010, 95e5, 100e5, 160e5
        res = accumulator(V, P1, P2, P3)
        assert res["ok"] is True
        assert res["precharge_ok"] is False
        assert len(res["warnings"]) > 0

    def test_precharge_ratio_compliant(self):
        """P1 = 0.85 × P2 must set precharge_ok=True."""
        P2, P3 = 100e5, 160e5
        P1 = 0.85 * P2
        res = accumulator(0.020, P1, P2, P3)
        assert res["ok"] is True
        assert res["precharge_ok"] is True

    def test_p2_le_p1_returns_error(self):
        res = accumulator(0.010, 120e5, 100e5, 160e5)
        assert res["ok"] is False

    def test_p3_le_p2_returns_error(self):
        res = accumulator(0.010, 70e5, 100e5, 90e5)
        assert res["ok"] is False

    def test_invalid_process_returns_error(self):
        res = accumulator(0.010, 70e5, 100e5, 160e5, process="polytropic")
        assert res["ok"] is False

    def test_delta_v_in_litres(self):
        """delta_V_L == delta_V_m3 × 1000."""
        res = accumulator(0.010, 70e5, 100e5, 150e5)
        assert abs(res["delta_V_L"] - res["delta_V_m3"] * 1000.0) < REL

    def test_n_exponent_isothermal(self):
        """Isothermal process → n_exponent = 1.0."""
        res = accumulator(0.010, 70e5, 100e5, 150e5, process="isothermal")
        assert res["n_exponent"] == 1.0

    def test_n_exponent_adiabatic(self):
        """Adiabatic process → n_exponent = 1.4."""
        res = accumulator(0.010, 70e5, 100e5, 150e5, process="adiabatic")
        assert res["n_exponent"] == 1.4


# ===========================================================================
# 5. valve_cv
# ===========================================================================

class TestValveCv:

    def test_cv_formula(self):
        """Cv = Q_gpm / √(ΔP_psi / SG)."""
        Q = 1e-3   # m³/s
        dP = 3e5   # Pa
        SG = 0.87
        res = valve_cv(Q, dP, SG)
        assert res["ok"] is True
        Q_gpm  = Q / 6.30902e-5
        dP_psi = dP / 6894.757
        Cv_expected = Q_gpm / math.sqrt(dP_psi / SG)
        assert abs(res["Cv"] - Cv_expected) / Cv_expected < REL

    def test_kv_formula(self):
        """Kv = Q_m3h / √(ΔP_bar / SG)."""
        Q = 5e-4
        dP = 2e5
        SG = 0.87
        res = valve_cv(Q, dP, SG)
        Q_m3h  = Q * 3600.0
        dP_bar = dP / 1e5
        Kv_expected = Q_m3h / math.sqrt(dP_bar / SG)
        assert abs(res["Kv"] - Kv_expected) / Kv_expected < REL

    def test_cv_kv_ratio(self):
        """Cv/Kv ≈ 1.156 (standard constant); allow 0.1% tolerance."""
        res = valve_cv(2e-3, 4e5, 0.87)
        ratio = res["Cv"] / res["Kv"]
        # The exact factor depends on unit-conversion chain; accept within 0.1%
        assert abs(ratio - 1.156) / 1.156 < 1e-3

    def test_zero_flow_returns_error(self):
        res = valve_cv(0.0, 2e5, 0.87)
        assert res["ok"] is False

    def test_negative_dp_returns_error(self):
        res = valve_cv(1e-3, -1e5, 0.87)
        assert res["ok"] is False

    def test_sg_zero_returns_error(self):
        res = valve_cv(1e-3, 2e5, 0.0)
        assert res["ok"] is False

    def test_primary_cv_when_metric_false(self):
        res = valve_cv(1e-3, 2e5, 0.87, metric=False)
        assert res["primary"] == "Cv"

    def test_primary_kv_when_metric_true(self):
        res = valve_cv(1e-3, 2e5, 0.87, metric=True)
        assert res["primary"] == "Kv"


# ===========================================================================
# 6. line_pressure_drop
# ===========================================================================

class TestLinePressureDrop:

    # Laminar (Re < 2300) tests

    def test_laminar_hagen_poiseuille(self):
        """Laminar: ΔP = 128μLQ / (πD⁴) — Hagen-Poiseuille."""
        Q, rho, mu, D, L = 1e-5, 870.0, 0.046, 0.010, 2.0
        res = line_pressure_drop(Q, rho, mu, D, L)
        # Check Re is laminar
        A = math.pi / 4.0 * D ** 2
        v = Q / A
        Re = rho * v * D / mu
        assert Re < 2300, f"expected laminar, Re={Re:.0f}"
        dP_expected = 128.0 * mu * L * Q / (math.pi * D ** 4)
        assert abs(res["delta_P_Pa"] - dP_expected) / dP_expected < REL

    def test_laminar_regime_label(self):
        Q, rho, mu, D, L = 1e-5, 870.0, 0.046, 0.010, 2.0
        res = line_pressure_drop(Q, rho, mu, D, L)
        assert res["regime"] == "laminar"

    def test_laminar_friction_factor(self):
        """Laminar Darcy f = 64 / Re."""
        Q, rho, mu, D, L = 1e-5, 870.0, 0.046, 0.010, 2.0
        res = line_pressure_drop(Q, rho, mu, D, L)
        A = math.pi / 4.0 * D ** 2
        v = Q / A
        Re = rho * v * D / mu
        assert abs(res["f_darcy"] - 64.0 / Re) / (64.0 / Re) < REL

    # Turbulent tests

    def test_turbulent_regime_label(self):
        """High Q gives turbulent flow."""
        Q, rho, mu, D, L = 5e-3, 870.0, 0.046, 0.012, 5.0
        res = line_pressure_drop(Q, rho, mu, D, L)
        assert res["regime"] == "turbulent"

    def test_pressure_drop_increases_with_flow(self):
        """Higher flow → higher pressure drop (both regimes)."""
        rho, mu, D, L = 870.0, 0.046, 0.010, 2.0
        dP1 = line_pressure_drop(1e-5, rho, mu, D, L)["delta_P_Pa"]
        dP2 = line_pressure_drop(2e-5, rho, mu, D, L)["delta_P_Pa"]
        assert dP2 > dP1

    def test_pressure_drop_increases_with_length(self):
        """Longer pipe → higher pressure drop."""
        Q, rho, mu, D = 1e-4, 870.0, 0.046, 0.015
        dP1 = line_pressure_drop(Q, rho, mu, D, 1.0)["delta_P_Pa"]
        dP2 = line_pressure_drop(Q, rho, mu, D, 2.0)["delta_P_Pa"]
        assert abs(dP2 / dP1 - 2.0) < 1e-6

    def test_fittings_Le_adds_to_length(self):
        """Adding fittings_Le must increase ΔP proportionally."""
        Q, rho, mu, D, L = 1e-5, 870.0, 0.046, 0.010, 2.0
        res_no_fittings = line_pressure_drop(Q, rho, mu, D, L, fittings_Le_m=0.0)
        res_fittings    = line_pressure_drop(Q, rho, mu, D, L, fittings_Le_m=2.0)
        # Laminar ΔP ∝ L_total → ratio should be ~2
        ratio = res_fittings["delta_P_Pa"] / res_no_fittings["delta_P_Pa"]
        assert abs(ratio - 2.0) < 1e-6

    def test_zero_diameter_returns_error(self):
        res = line_pressure_drop(1e-4, 870.0, 0.046, 0.0, 1.0)
        assert res["ok"] is False

    def test_negative_length_returns_error(self):
        res = line_pressure_drop(1e-4, 870.0, 0.046, 0.010, -1.0)
        assert res["ok"] is False

    def test_delta_p_bar_consistent(self):
        """delta_P_bar == delta_P_Pa / 1e5."""
        Q, rho, mu, D, L = 2e-4, 870.0, 0.046, 0.015, 3.0
        res = line_pressure_drop(Q, rho, mu, D, L)
        assert abs(res["delta_P_bar"] - res["delta_P_Pa"] / 1e5) < 1e-10


# ===========================================================================
# 7. line_size
# ===========================================================================

class TestLineSize:

    def test_d_min_at_v_max_pressure(self):
        """D_min = √(4Q/(π × v_max)) for pressure line (v_max=6 m/s)."""
        Q = 1e-3
        v_max = 6.0
        D_min_expected = math.sqrt(4.0 * Q / (math.pi * v_max))
        res = line_size(Q, service="pressure")
        assert abs(res["D_min_m"] - D_min_expected) / D_min_expected < REL

    def test_d_min_at_v_max_suction(self):
        """D_min = √(4Q/(π × v_max)) for suction line (v_max=1.5 m/s)."""
        Q = 5e-4
        v_max = 1.5
        D_min_expected = math.sqrt(4.0 * Q / (math.pi * v_max))
        res = line_size(Q, service="suction")
        assert abs(res["D_min_m"] - D_min_expected) / D_min_expected < REL

    def test_d_rec_larger_than_d_min(self):
        """Recommended bore > minimum bore (lower velocity)."""
        res = line_size(2e-3, service="pressure")
        assert res["D_rec_m"] > res["D_min_m"]

    def test_d_rec_mm_consistent(self):
        """D_rec_mm == D_rec_m × 1000."""
        res = line_size(1e-3, service="return")
        assert abs(res["D_rec_mm"] - res["D_rec_m"] * 1000.0) < REL

    def test_invalid_service_returns_error(self):
        res = line_size(1e-3, service="drain")
        assert res["ok"] is False

    def test_zero_flow_returns_error(self):
        res = line_size(0.0)
        assert res["ok"] is False


# ===========================================================================
# 8. reservoir
# ===========================================================================

class TestReservoir:

    def test_volume_formula(self):
        """V_reservoir = rule_factor × Q [m³/min]."""
        Q = 5e-4   # m³/s
        rf = 3.0
        res = reservoir(Q, rule_factor=rf)
        assert res["ok"] is True
        V_expected = rf * (Q * 60.0)
        assert abs(res["V_reservoir_m3"] - V_expected) / V_expected < REL

    def test_default_rule_factor_is_3(self):
        """Default rule_factor=3 matches explicit rule_factor=3."""
        Q = 1e-3
        res_default = reservoir(Q)
        res_explicit = reservoir(Q, rule_factor=3.0)
        assert abs(res_default["V_reservoir_m3"] - res_explicit["V_reservoir_m3"]) < REL

    def test_larger_rule_factor_gives_larger_reservoir(self):
        Q = 2e-3
        V3 = reservoir(Q, rule_factor=3.0)["V_reservoir_m3"]
        V5 = reservoir(Q, rule_factor=5.0)["V_reservoir_m3"]
        assert V5 > V3

    def test_volume_litres_consistent(self):
        """V_reservoir_L == V_reservoir_m3 × 1000."""
        res = reservoir(1e-3, rule_factor=3.0)
        assert abs(res["V_reservoir_L"] - res["V_reservoir_m3"] * 1000.0) < REL

    def test_zero_flow_returns_error(self):
        res = reservoir(0.0)
        assert res["ok"] is False

    def test_zero_rule_factor_returns_error(self):
        res = reservoir(1e-3, rule_factor=0.0)
        assert res["ok"] is False


# ===========================================================================
# 9. thermal_balance
# ===========================================================================

class TestThermalBalance:

    def test_heat_generated_formula(self):
        """Q_heat = P_input × (1 - η)."""
        P, eta = 50000.0, 0.85
        res = thermal_balance(P, eta)
        assert res["ok"] is True
        assert abs(res["Q_heat_W"] - P * (1.0 - eta)) < 1e-6

    def test_surface_cooling_formula(self):
        """Q_surface = U × A × ΔT."""
        P, eta, A, U, dT = 50000.0, 0.85, 4.0, 10.0, 40.0
        res = thermal_balance(P, eta, area_m2=A, U_Wm2K=U, dT_K=dT)
        Q_surf = U * A * dT
        assert abs(res["Q_surface_W"] - Q_surf) < 1e-6

    def test_cooler_formula(self):
        """Q_cooler = ρ × Q_cool × cp × ΔT."""
        P, eta = 100000.0, 0.80
        Q_cool, cp, rho, dT = 5e-3, 1880.0, 870.0, 40.0
        res = thermal_balance(
            P, eta,
            cooling_flow_m3s=Q_cool,
            fluid_cp=cp, fluid_rho=rho, dT_K=dT
        )
        Q_cooler = rho * Q_cool * cp * dT
        assert abs(res["Q_cooler_W"] - Q_cooler) / Q_cooler < REL

    def test_balanced_when_dissipation_exceeds_heat(self):
        """System balanced when Q_dissipated >= Q_heat."""
        # Large cooling area ensures balance
        res = thermal_balance(5000.0, 0.90, area_m2=20.0, dT_K=40.0)
        assert res["thermal_balanced"] is True

    def test_unbalanced_when_heat_exceeds_dissipation(self):
        """Without cooling, a high-loss system must be flagged as unbalanced."""
        # Very high power, low efficiency, no cooling area provided
        res = thermal_balance(500000.0, 0.50)
        # No area and no cooler → Q_dissipated = 0
        assert res["thermal_balanced"] is False
        assert res["Q_total_dissipated_W"] == 0.0
        assert len(res["warnings"]) > 0

    def test_heat_surplus_negative_when_unbalanced(self):
        res = thermal_balance(200000.0, 0.60)
        assert res["heat_surplus_W"] < 0.0

    def test_total_dissipated_is_sum(self):
        """Q_total = Q_surface + Q_cooler."""
        res = thermal_balance(
            50000.0, 0.85,
            area_m2=2.0, cooling_flow_m3s=1e-3, dT_K=40.0
        )
        total = res["Q_surface_W"] + res["Q_cooler_W"]
        assert abs(res["Q_total_dissipated_W"] - total) < 1e-6

    def test_zero_input_power_returns_error(self):
        res = thermal_balance(0.0, 0.85)
        assert res["ok"] is False

    def test_efficiency_above_one_returns_error(self):
        res = thermal_balance(10000.0, 1.05)
        assert res["ok"] is False


# ===========================================================================
# 10. LLM tool wrappers
# ===========================================================================

class TestToolWrappers:

    def test_run_fp_cylinder_happy_path(self):
        ctx = _ctx()
        raw = _run(run_fp_cylinder(ctx, _args(
            bore_m=0.10, rod_m=0.05, pressure_Pa=10e6, flow_m3s=1e-3
        )))
        d = _ok_tool(raw)
        assert d["F_extend_N"] > 0
        assert d["v_extend_ms"] > 0

    def test_run_fp_cylinder_missing_bore(self):
        ctx = _ctx()
        raw = _run(run_fp_cylinder(ctx, _args(
            rod_m=0.05, pressure_Pa=10e6, flow_m3s=1e-3
        )))
        _err_tool(raw)

    def test_run_fp_pump_happy_path(self):
        ctx = _ctx()
        raw = _run(run_fp_pump(ctx, _args(
            displacement_m3=20e-6, rpm=1500.0, vol_eff=0.92,
            overall_eff=0.85, pressure_Pa=20e6
        )))
        d = _ok_tool(raw)
        assert d["Q_actual_m3s"] > 0
        assert d["P_input_W"] > 0

    def test_run_fp_pump_bad_json(self):
        ctx = _ctx()
        raw = _run(run_fp_pump(ctx, b"not json"))
        _err_tool(raw)

    def test_run_fp_motor_happy_path(self):
        ctx = _ctx()
        raw = _run(run_fp_motor(ctx, _args(
            displacement_m3=50e-6, pressure_Pa=15e6, rpm=1000.0
        )))
        d = _ok_tool(raw)
        assert d["T_output_Nm"] > 0
        assert d["P_output_W"] > 0

    def test_run_fp_accumulator_isothermal(self):
        ctx = _ctx()
        raw = _run(run_fp_accumulator(ctx, _args(
            V_total_m3=0.010, P1_Pa=70e5, P2_Pa=100e5, P3_Pa=160e5,
            process="isothermal"
        )))
        d = _ok_tool(raw)
        assert d["delta_V_m3"] > 0
        assert d["delta_V_L"] > 0

    def test_run_fp_accumulator_missing_p2(self):
        ctx = _ctx()
        raw = _run(run_fp_accumulator(ctx, _args(
            V_total_m3=0.010, P1_Pa=70e5, P3_Pa=160e5
        )))
        _err_tool(raw)

    def test_run_fp_valve_cv_happy_path(self):
        ctx = _ctx()
        raw = _run(run_fp_valve_cv(ctx, _args(
            Q_m3s=1e-3, delta_P_Pa=3e5, SG=0.87
        )))
        d = _ok_tool(raw)
        assert d["Cv"] > 0
        assert d["Kv"] > 0

    def test_run_fp_line_pressure_drop_laminar(self):
        ctx = _ctx()
        raw = _run(run_fp_line_pressure_drop(ctx, _args(
            Q_m3s=1e-5, rho=870.0, mu=0.046, D_i_m=0.010, L_m=2.0
        )))
        d = _ok_tool(raw)
        assert d["regime"] == "laminar"
        assert d["delta_P_Pa"] > 0

    def test_run_fp_line_pressure_drop_missing_rho(self):
        ctx = _ctx()
        raw = _run(run_fp_line_pressure_drop(ctx, _args(
            Q_m3s=1e-5, mu=0.046, D_i_m=0.010, L_m=2.0
        )))
        _err_tool(raw)

    def test_run_fp_line_size_happy_path(self):
        ctx = _ctx()
        raw = _run(run_fp_line_size(ctx, _args(Q_m3s=2e-3, service="pressure")))
        d = _ok_tool(raw)
        assert d["D_min_mm"] > 0
        assert d["D_rec_mm"] > d["D_min_mm"]

    def test_run_fp_reservoir_happy_path(self):
        ctx = _ctx()
        raw = _run(run_fp_reservoir(ctx, _args(pump_flow_m3s=5e-4, rule_factor=3.0)))
        d = _ok_tool(raw)
        assert d["V_reservoir_L"] > 0

    def test_run_fp_reservoir_missing_flow(self):
        ctx = _ctx()
        raw = _run(run_fp_reservoir(ctx, _args(rule_factor=3.0)))
        _err_tool(raw)

    def test_run_fp_thermal_balance_happy_path(self):
        ctx = _ctx()
        raw = _run(run_fp_thermal_balance(ctx, _args(
            input_power_W=50000.0, eff_overall=0.85,
            area_m2=5.0, dT_K=40.0
        )))
        d = _ok_tool(raw)
        assert "thermal_balanced" in d
        assert "Q_heat_W" in d

    def test_run_fp_thermal_balance_missing_eff(self):
        ctx = _ctx()
        raw = _run(run_fp_thermal_balance(ctx, _args(input_power_W=50000.0)))
        _err_tool(raw)


# ===========================================================================
# 11. CITABLE EXTERNAL-REFERENCE CASES — known numeric answers
# ===========================================================================
#
# Cross-checked against published fluid-power texts / NFPA conventions with
# hand-computable answers.  These pin the load-bearing constants and exponents.
#
# Sources
# -------
# [Vickers] Vickers/Eaton "Industrial Hydraulics Manual", 5th ed. (2008).
# [Parker]  Parker Hannifin "Industrial Hydraulics Design Guide" (rev 2022).
# [ISA]     ISA-75.01.01 / IEC 60534-2-1 — valve flow-coefficient definition.
# [White]   White, F.M., "Fluid Mechanics", 8th ed. — Hagen–Poiseuille.
# [Boyle]   Boyle's law (isothermal accumulator, Parker/Bosch-Rexroth form).
# ===========================================================================

class TestCitableReferenceCases:

    def test_ref_cylinder_force_vickers_2in_1000psi(self):
        """[Vickers] 2 in bore (0.0508 m) at 1000 psi (6.895 MPa):
        A_bore = π/4·0.0508² = 2.02683e-3 m²,
        F = 6.895e6 · 2.02683e-3 = 13974.99 N  (≈ 3142 lbf).
        """
        res = cylinder(0.0508, 0.0254, 6.895e6, 1e-3)
        assert res["ok"] is True
        A = math.pi / 4.0 * 0.0508 ** 2
        assert res["A_bore_m2"] == pytest.approx(A, rel=1e-12)
        assert res["F_extend_N"] == pytest.approx(6.895e6 * A, rel=1e-9)
        assert res["F_extend_N"] == pytest.approx(13974.99, rel=1e-5)

    def test_ref_pump_flow_displacement_law(self):
        """[Vickers] Pump theoretical delivery Q = D·n.
        D=100 cm³/rev = 1e-4 m³/rev, n=1500 rpm (25 rev/s), η_v=1.0
        → Q = 1e-4·25 = 2.5e-3 m³/s = 150 L/min.
        """
        res = pump(1e-4, 1500.0, 1.0, 1.0, 1e7)
        assert res["ok"] is True
        assert res["Q_actual_m3s"] == pytest.approx(2.5e-3, rel=1e-12)
        assert res["Q_actual_m3s"] * 60000.0 == pytest.approx(150.0, rel=1e-9)
        assert res["P_hydraulic_W"] == pytest.approx(1e7 * 2.5e-3, rel=1e-12)

    def test_ref_motor_torque_displacement_law(self):
        """[Parker] Ideal motor torque T = D·ΔP/(2π).
        D=200 cm³/rev = 2e-4 m³/rev, ΔP=20 MPa
        → T = 2e-4·2e7/(2π) = 636.6198 N·m.
        """
        res = motor(2e-4, 2e7, 1000.0, mech_eff=1.0)
        assert res["ok"] is True
        assert res["T_theoretical_Nm"] == pytest.approx(636.6198, abs=1e-4)

    def test_ref_valve_cv_isa_defining_case(self):
        """[ISA] Defining Cv: 1 US gpm water (SG=1) at 1 psi ΔP gives Cv=1.
        100 gpm water at 100 psi, SG=1 → Cv = 100/√(100/1) = 10.0 exactly.
        """
        Q = 100.0 * 6.30902e-5      # 100 gpm → m³/s
        dP = 100.0 * 6894.757       # 100 psi → Pa
        res = valve_cv(Q, dP, 1.0)
        assert res["ok"] is True
        assert res["Cv"] == pytest.approx(10.0, rel=1e-6)

    def test_ref_accumulator_boyle_isothermal(self):
        """[Boyle] Isothermal usable volume ΔV = V·P1·(1/P2 − 1/P3).
        V=0.010 m³, P1=70 bar, P2=100 bar, P3=160 bar
        → ΔV = 0.01·70e5·(1/100e5 − 1/160e5) = 2.625e-3 m³.
        """
        res = accumulator(0.010, 70e5, 100e5, 160e5, process="isothermal")
        assert res["ok"] is True
        hand = 0.010 * 70e5 * (1.0 / 100e5 - 1.0 / 160e5)
        assert res["delta_V_m3"] == pytest.approx(hand, rel=1e-12)
        assert res["delta_V_m3"] == pytest.approx(2.625e-3, rel=1e-9)

    def test_ref_line_pressure_drop_hagen_poiseuille(self):
        """[White §6.4] Laminar pipe ΔP = 128·μ·L·Q/(π·D⁴).
        Q=1e-5 m³/s, μ=0.046 Pa·s, L=2 m, D=0.010 m (Re≈24, laminar)
        → ΔP = 128·0.046·2·1e-5/(π·0.010⁴) = 3748.4172 Pa.
        """
        res = line_pressure_drop(1e-5, 870.0, 0.046, 0.010, 2.0)
        assert res["ok"] is True
        assert res["regime"] == "laminar"
        hand = 128.0 * 0.046 * 2.0 * 1e-5 / (math.pi * 0.010 ** 4)
        assert res["delta_P_Pa"] == pytest.approx(hand, rel=1e-12)
        assert res["delta_P_Pa"] == pytest.approx(3748.4172, abs=1e-3)
        assert res["f_darcy"] == pytest.approx(64.0 / res["Re"], rel=1e-12)
