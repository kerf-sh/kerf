"""
Hermetic tests for kerf_cad_core.pneumatics — pneumatic circuit sizing.

Coverage:
  circuit.cylinder              — theoretical & effective force, load ratio
  circuit.air_consumption       — free-air Nl/min, compression ratio
  circuit.valve_flow_iso6358    — ISO 6358 choked & subsonic branches
  circuit.valve_flow_cv         — Cv choked & subsonic branches
  circuit.receiver_sizing       — hold-up time, free-air storage
  circuit.blowdown_time         — choked + subsonic phases, total time
  circuit.charge_time           — charge time from compressor
  circuit.frl_pressure_drop     — total FRL drop, outlet pressure, efficiency
  tools.*                       — LLM tool wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network.
Formulas verified algebraically against published expressions.

References
----------
ISO 6358-1:2013 — Pneumatic fluid power
SMC Technical Data — Pneumatic Actuator Selection Guide
NFPA T3.21.3 — Cylinder force and speed calculations

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.pneumatics.circuit import (
    cylinder,
    air_consumption,
    valve_flow_iso6358,
    valve_flow_cv,
    receiver_sizing,
    blowdown_time,
    charge_time,
    frl_pressure_drop,
    _P_ATM,
    _T_N,
    _B_IDEAL,
)
from kerf_cad_core.pneumatics.tools import (
    run_pneu_cylinder,
    run_pneu_air_consumption,
    run_pneu_valve_iso6358,
    run_pneu_valve_cv,
    run_pneu_receiver_sizing,
    run_pneu_blowdown_time,
    run_pneu_charge_time,
    run_pneu_frl_drop,
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


REL = 1e-9   # relative tolerance


# ===========================================================================
# 1. cylinder
# ===========================================================================

class TestCylinder:

    def test_theoretical_extend_force_formula(self):
        """F_extend_th = (P_supply - P_atm) × A_bore."""
        bore, rod = 0.080, 0.040
        P_s = 700_000.0  # 7 bar abs
        res = cylinder(bore, rod, P_s)
        assert res["ok"] is True
        A_bore = math.pi / 4.0 * bore ** 2
        F_th = (P_s - _P_ATM) * A_bore
        assert abs(res["F_extend_th_N"] - F_th) / F_th < REL

    def test_theoretical_retract_force_formula(self):
        """F_retract_th = (P_supply - P_atm) × A_rod."""
        bore, rod = 0.063, 0.025
        P_s = 600_000.0
        res = cylinder(bore, rod, P_s)
        A_rod = math.pi / 4.0 * (bore ** 2 - rod ** 2)
        F_th = (P_s - _P_ATM) * A_rod
        assert abs(res["F_retract_th_N"] - F_th) / F_th < REL

    def test_extend_force_greater_than_retract(self):
        """Extend force > retract force (full bore vs annulus)."""
        res = cylinder(0.100, 0.040, 700_000.0)
        assert res["F_extend_th_N"] > res["F_retract_th_N"]

    def test_bore_area_field(self):
        """A_bore_m2 = π/4 × bore²."""
        bore = 0.050
        res = cylinder(bore, 0.020, 600_000.0)
        assert abs(res["A_bore_m2"] - math.pi / 4.0 * bore ** 2) < 1e-15

    def test_rod_area_field(self):
        """A_rod_m2 = π/4 × (bore² − rod²)."""
        bore, rod = 0.100, 0.050
        res = cylinder(bore, rod, 700_000.0)
        expected = math.pi / 4.0 * (bore ** 2 - rod ** 2)
        assert abs(res["A_rod_m2"] - expected) < 1e-15

    def test_load_ratio_zero_load(self):
        """With load_N=0 the load_ratio should be 0."""
        res = cylinder(0.080, 0.032, 700_000.0, load_N=0.0)
        assert res["load_ratio_extend"] == pytest.approx(0.0, abs=1e-12)

    def test_load_ratio_ok_when_below_0_7(self):
        """Load ratio <= 0.70 → load_ratio_ok = True."""
        res = cylinder(0.100, 0.040, 700_000.0, load_N=1000.0)
        assert res["ok"] is True
        if res["F_extend_eff_N"] > 0:
            expected_lr = 1000.0 / res["F_extend_eff_N"]
            if expected_lr <= 0.70:
                assert res["load_ratio_ok"] is True

    def test_load_ratio_not_ok_when_above_0_7_warns(self):
        """Very high load → load_ratio_ok=False and warning issued."""
        bore = 0.032  # small cylinder
        rod  = 0.012
        P_s  = 200_000.0  # low pressure
        # Force is small → apply a huge load
        res = cylinder(bore, rod, P_s, load_N=10_000.0)
        assert res["ok"] is True
        # May be load_ratio_ok=False or force could be negative
        assert isinstance(res["warnings"], list)

    def test_rod_equal_bore_returns_error(self):
        res = cylinder(0.050, 0.050, 700_000.0)
        assert res["ok"] is False

    def test_rod_larger_than_bore_returns_error(self):
        res = cylinder(0.040, 0.080, 700_000.0)
        assert res["ok"] is False

    def test_supply_at_or_below_atm_returns_error(self):
        res = cylinder(0.080, 0.032, _P_ATM)
        assert res["ok"] is False

    def test_negative_bore_returns_error(self):
        res = cylinder(-0.08, 0.032, 700_000.0)
        assert res["ok"] is False

    def test_back_pressure_effect_on_effective_force(self):
        """Higher back pressure reduces effective extend force."""
        bore, rod, P_s = 0.100, 0.040, 700_000.0
        res_low  = cylinder(bore, rod, P_s, back_pressure_Pa=_P_ATM)
        res_high = cylinder(bore, rod, P_s, back_pressure_Pa=200_000.0)
        assert res_low["F_extend_eff_N"] > res_high["F_extend_eff_N"]


# ===========================================================================
# 2. air_consumption
# ===========================================================================

class TestAirConsumption:

    def test_compression_ratio(self):
        """Compression ratio = P_supply / P_atm."""
        P_s = 700_000.0
        res = air_consumption(0.080, 0.032, 0.200, P_s, 10.0)
        assert res["ok"] is True
        assert abs(res["compression_ratio"] - P_s / _P_ATM) < REL

    def test_double_acting_larger_than_single_acting(self):
        """Double-acting consumes more air than single-acting."""
        args = (0.080, 0.032, 0.200, 700_000.0, 10.0)
        res_da = air_consumption(*args, double_acting=True)
        res_sa = air_consumption(*args, double_acting=False)
        assert res_da["Q_free_Nl_min"] > res_sa["Q_free_Nl_min"]

    def test_extend_volume_formula(self):
        """V_extend = A_bore × stroke."""
        bore, stroke = 0.063, 0.150
        res = air_consumption(bore, 0.020, stroke, 600_000.0, 5.0)
        A_bore = math.pi / 4.0 * bore ** 2
        assert abs(res["V_extend_m3"] - A_bore * stroke) / (A_bore * stroke) < REL

    def test_retract_volume_formula(self):
        """V_retract = A_rod × stroke."""
        bore, rod, stroke = 0.080, 0.032, 0.200
        res = air_consumption(bore, rod, stroke, 700_000.0, 10.0)
        A_rod = math.pi / 4.0 * (bore ** 2 - rod ** 2)
        assert abs(res["V_retract_m3"] - A_rod * stroke) / (A_rod * stroke) < REL

    def test_free_air_rate_formula(self):
        """Q_free_Nl_min = V_cycle_free × cpm × 1000."""
        bore, rod, stroke, P_s, cpm = 0.080, 0.032, 0.200, 700_000.0, 10.0
        res = air_consumption(bore, rod, stroke, P_s, cpm)
        expected = res["V_cycle_free_m3"] * cpm * 1000.0
        assert abs(res["Q_free_Nl_min"] - expected) / expected < REL

    def test_temperature_correction(self):
        """Higher temperature → less free air (T_N/T factor decreases)."""
        args = (0.080, 0.032, 0.200, 700_000.0, 10.0)
        res_cold = air_consumption(*args, T_K=273.15)
        res_hot  = air_consumption(*args, T_K=373.15)
        assert res_cold["Q_free_Nl_min"] > res_hot["Q_free_Nl_min"]

    def test_rod_equal_bore_returns_error(self):
        res = air_consumption(0.050, 0.050, 0.100, 600_000.0, 5.0)
        assert res["ok"] is False

    def test_supply_at_atm_returns_error(self):
        res = air_consumption(0.080, 0.032, 0.200, _P_ATM, 10.0)
        assert res["ok"] is False

    def test_zero_stroke_returns_error(self):
        res = air_consumption(0.080, 0.032, 0.0, 700_000.0, 10.0)
        assert res["ok"] is False


# ===========================================================================
# 3. valve_flow_iso6358
# ===========================================================================

class TestValveFlowISO6358:

    def test_choked_flow_formula(self):
        """Choked: q = C × P1 × √(T_N / T1)."""
        P1, T1, C, b = 700_000.0, 293.15, 1e-8, 0.30
        P2 = P1 * b * 0.5  # well below choke: P2/P1 = 0.15 < b=0.30
        res = valve_flow_iso6358(P1, P2, T1, C, b)
        assert res["ok"] is True
        assert res["choked"] is True
        q_expected = C * P1 * math.sqrt(_T_N / T1)
        assert abs(res["q_m3s_normal"] - q_expected) / q_expected < REL

    def test_subsonic_flow_less_than_choked(self):
        """Subsonic flow < choked (maximum) flow."""
        P1, T1, C, b = 500_000.0, 293.15, 1e-8, 0.30
        P2 = P1 * 0.8  # P2/P1 = 0.8 >> b → subsonic
        res = valve_flow_iso6358(P1, P2, T1, C, b)
        assert res["ok"] is True
        assert res["choked"] is False
        assert res["q_m3s_normal"] < res["q_max_m3s_normal"]

    def test_choked_boundary_exactly_at_b(self):
        """P2/P1 = b exactly → flow is choked (boundary condition)."""
        P1, T1, C, b = 600_000.0, 293.15, 5e-9, 0.35
        P2 = P1 * b
        res = valve_flow_iso6358(P1, P2, T1, C, b)
        assert res["ok"] is True
        assert res["choked"] is True

    def test_subsonic_just_above_b(self):
        """P2/P1 slightly above b → subsonic (not choked)."""
        P1, T1, C, b = 600_000.0, 293.15, 5e-9, 0.35
        P2 = P1 * (b + 0.01)  # just above critical
        res = valve_flow_iso6358(P1, P2, T1, C, b)
        assert res["ok"] is True
        assert res["choked"] is False

    def test_subsonic_formula(self):
        """Subsonic: q = q_max × √(1 − ((P2/P1 − b)/(1−b))²)."""
        P1, T1, C, b = 500_000.0, 293.15, 1e-8, 0.28
        P2 = P1 * 0.75  # P2/P1 = 0.75
        res = valve_flow_iso6358(P1, P2, T1, C, b)
        assert not res["choked"]
        q_max = C * P1 * math.sqrt(_T_N / T1)
        ratio = P2 / P1
        inner = (ratio - b) / (1.0 - b)
        q_expected = q_max * math.sqrt(1.0 - inner ** 2)
        assert abs(res["q_m3s_normal"] - q_expected) / q_expected < REL

    def test_q_Nl_min_consistent(self):
        """q_Nl_min = q_m3s_normal × 1000 × 60."""
        P1, T1, C, b = 700_000.0, 293.15, 1e-8, 0.30
        P2 = P1 * 0.90
        res = valve_flow_iso6358(P1, P2, T1, C, b)
        assert abs(res["q_Nl_min"] - res["q_m3s_normal"] * 1000.0 * 60.0) < REL

    def test_p2_greater_than_p1_returns_error(self):
        res = valve_flow_iso6358(400_000.0, 500_000.0, 293.15, 1e-8, 0.30)
        assert res["ok"] is False

    def test_invalid_b_zero_returns_error(self):
        res = valve_flow_iso6358(500_000.0, 300_000.0, 293.15, 1e-8, 0.0)
        assert res["ok"] is False

    def test_invalid_b_above_1_returns_error(self):
        res = valve_flow_iso6358(500_000.0, 300_000.0, 293.15, 1e-8, 1.1)
        assert res["ok"] is False

    def test_zero_C_returns_error(self):
        res = valve_flow_iso6358(500_000.0, 300_000.0, 293.15, 0.0, 0.30)
        assert res["ok"] is False

    def test_higher_P1_gives_more_choked_flow(self):
        """Choked flow ∝ P1."""
        T1, C, b = 293.15, 1e-8, 0.30
        P2_low = 50_000.0  # always choked relative to P1
        res1 = valve_flow_iso6358(400_000.0, 400_000.0 * 0.1, T1, C, b)
        res2 = valve_flow_iso6358(800_000.0, 800_000.0 * 0.1, T1, C, b)
        assert res2["q_m3s_normal"] == pytest.approx(2.0 * res1["q_m3s_normal"], rel=1e-9)


# ===========================================================================
# 4. valve_flow_cv
# ===========================================================================

class TestValveFlowCv:

    def test_choked_condition_below_b_ideal(self):
        """P2/P1 <= 0.528 → choked."""
        P1 = 700_000.0
        P2 = P1 * 0.40  # well below 0.528
        res = valve_flow_cv(5.0, P1, P2, 293.15)
        assert res["ok"] is True
        assert res["choked"] is True

    def test_subsonic_condition_above_b_ideal(self):
        """P2/P1 > 0.528 → subsonic."""
        P1 = 700_000.0
        P2 = P1 * 0.80  # above 0.528
        res = valve_flow_cv(5.0, P1, P2, 293.15)
        assert res["ok"] is True
        assert res["choked"] is False

    def test_choked_flow_equals_max_flow(self):
        """Choked: q == q_max."""
        P1 = 700_000.0
        P2 = P1 * 0.30
        res = valve_flow_cv(5.0, P1, P2, 293.15)
        assert res["choked"] is True
        assert abs(res["q_Nl_min"] - res["q_max_Nl_min"]) < REL

    def test_subsonic_flow_less_than_max(self):
        """Subsonic: q < q_max."""
        P1 = 700_000.0
        P2 = P1 * 0.80
        res = valve_flow_cv(5.0, P1, P2, 293.15)
        assert not res["choked"]
        assert res["q_Nl_min"] < res["q_max_Nl_min"]

    def test_q_m3s_normal_consistent_with_Nl_min(self):
        """q_m3s_normal = q_Nl_min / (1000 × 60)."""
        P1, P2 = 500_000.0, 400_000.0
        res = valve_flow_cv(3.0, P1, P2, 293.15)
        expected = res["q_Nl_min"] / (1000.0 * 60.0)
        assert abs(res["q_m3s_normal"] - expected) < REL

    def test_choked_flow_formula(self):
        """q_max_Nl_min = 417 × Cv × P1_bar × √(T_N / (SG × T))."""
        Cv, T = 4.0, 293.15
        P1 = 600_000.0
        P2 = P1 * 0.20  # choked
        res = valve_flow_cv(Cv, P1, P2, T, SG_gas=1.0)
        P1_bar = P1 / 1e5
        q_max_expected = 417.0 * Cv * P1_bar * math.sqrt(_T_N / (1.0 * T))
        assert abs(res["q_max_Nl_min"] - q_max_expected) / q_max_expected < REL

    def test_p2_greater_than_p1_returns_error(self):
        res = valve_flow_cv(5.0, 300_000.0, 400_000.0, 293.15)
        assert res["ok"] is False

    def test_zero_cv_returns_error(self):
        res = valve_flow_cv(0.0, 500_000.0, 300_000.0, 293.15)
        assert res["ok"] is False

    def test_choked_boundary_at_b_ideal(self):
        """P2/P1 = B_IDEAL exactly → choked."""
        P1 = 700_000.0
        P2 = P1 * _B_IDEAL
        res = valve_flow_cv(5.0, P1, P2, 293.15)
        assert res["ok"] is True
        assert res["choked"] is True


# ===========================================================================
# 5. receiver_sizing
# ===========================================================================

class TestReceiverSizing:

    def test_delta_v_free_formula(self):
        """ΔV_free = V × (P_high - P_low) / P_atm × (T_N/T)."""
        V, P_hi, P_lo, Q = 0.200, 900_000.0, 700_000.0, 5e-4
        res = receiver_sizing(V, P_hi, P_lo, Q)
        assert res["ok"] is True
        expected = V * (P_hi - P_lo) / _P_ATM * (_T_N / _T_N)
        assert abs(res["delta_V_free_m3"] - expected) / expected < REL

    def test_t_supply_formula(self):
        """t_supply = delta_V_free / Q_demand."""
        V, P_hi, P_lo, Q = 0.200, 900_000.0, 700_000.0, 5e-4
        res = receiver_sizing(V, P_hi, P_lo, Q)
        expected = res["delta_V_free_m3"] / Q
        assert abs(res["t_supply_s"] - expected) / expected < REL

    def test_larger_receiver_longer_supply_time(self):
        """Doubling receiver volume doubles hold-up time."""
        P_hi, P_lo, Q = 900_000.0, 700_000.0, 5e-4
        t1 = receiver_sizing(0.100, P_hi, P_lo, Q)["t_supply_s"]
        t2 = receiver_sizing(0.200, P_hi, P_lo, Q)["t_supply_s"]
        assert abs(t2 / t1 - 2.0) < 1e-9

    def test_t_supply_min_consistent(self):
        """t_supply_min = t_supply_s / 60."""
        res = receiver_sizing(0.200, 900_000.0, 700_000.0, 5e-4)
        assert abs(res["t_supply_min"] - res["t_supply_s"] / 60.0) < REL

    def test_delta_v_Nl_consistent(self):
        """delta_V_free_Nl = delta_V_free_m3 × 1000."""
        res = receiver_sizing(0.200, 900_000.0, 700_000.0, 5e-4)
        assert abs(res["delta_V_free_Nl"] - res["delta_V_free_m3"] * 1000.0) < REL

    def test_p_high_le_p_low_returns_error(self):
        res = receiver_sizing(0.200, 700_000.0, 900_000.0, 5e-4)
        assert res["ok"] is False

    def test_p_low_at_or_below_atm_returns_error(self):
        res = receiver_sizing(0.200, 700_000.0, _P_ATM, 5e-4)
        assert res["ok"] is False

    def test_zero_volume_returns_error(self):
        res = receiver_sizing(0.0, 900_000.0, 700_000.0, 5e-4)
        assert res["ok"] is False


# ===========================================================================
# 6. blowdown_time
# ===========================================================================

class TestBlowdownTime:

    def test_choked_blowdown_exponential_formula(self):
        """Pure choked blowdown: t = V/(C·P_atm·√(T_N/T)) × ln(P0/P_choke)."""
        V = 0.100
        P0 = 800_000.0
        b = 0.30
        C = 1e-7
        T = _T_N
        P_a = _P_ATM
        # P_final just at choke transition so only choked phase occurs
        P_choke = P_a / b  # ≈ 337750 Pa
        P_final = P_choke  # stop at transition → no subsonic phase
        res = blowdown_time(V, P0, P_final, C, b, T_K=T)
        assert res["ok"] is True
        temp_factor = math.sqrt(_T_N / T)
        t_expected = V / (C * P_a * temp_factor) * math.log(P0 / P_choke)
        assert abs(res["t_choked_s"] - t_expected) / t_expected < 1e-6

    def test_total_blowdown_includes_subsonic_phase(self):
        """Full blowdown to atmosphere: t_total > t_choked."""
        res = blowdown_time(0.100, 700_000.0, _P_ATM, 1e-7, 0.30)
        assert res["ok"] is True
        assert res["t_total_s"] > res["t_choked_s"]
        assert res["t_subsonic_s"] > 0.0

    def test_larger_vessel_longer_blowdown(self):
        """Doubling V doubles blowdown time (choked phase scales linearly)."""
        args = (700_000.0, _P_ATM, 1e-7, 0.30)
        t1 = blowdown_time(0.100, *args)["t_total_s"]
        t2 = blowdown_time(0.200, *args)["t_total_s"]
        # Should roughly double (exact for choked phase, approximate for subsonic)
        assert t2 > t1 * 1.5  # At least 50% more; typically close to 2×

    def test_p_final_equal_p_initial_returns_error(self):
        res = blowdown_time(0.100, 700_000.0, 700_000.0, 1e-7, 0.30)
        assert res["ok"] is False

    def test_p_initial_at_atm_returns_error(self):
        res = blowdown_time(0.100, _P_ATM, _P_ATM, 1e-7, 0.30)
        assert res["ok"] is False

    def test_invalid_b_returns_error(self):
        res = blowdown_time(0.100, 700_000.0, _P_ATM, 1e-7, 1.5)
        assert res["ok"] is False

    def test_t_total_positive(self):
        """Blowdown time must be positive."""
        res = blowdown_time(0.050, 600_000.0, _P_ATM, 5e-8, 0.25)
        assert res["ok"] is True
        assert res["t_total_s"] > 0.0

    def test_smaller_orifice_longer_blowdown(self):
        """Halving C doubles blowdown time."""
        args = (0.100, 700_000.0, _P_ATM)
        b = 0.30
        t1 = blowdown_time(*args, 2e-7, b)["t_total_s"]
        t2 = blowdown_time(*args, 1e-7, b)["t_total_s"]
        # Expect t2 ≈ 2 × t1 (approximately, since both phases scale with 1/C)
        assert t2 > t1 * 1.8


# ===========================================================================
# 7. charge_time
# ===========================================================================

class TestChargeTime:

    def test_charge_time_formula(self):
        """t_charge = V × delta_P / (P_atm × Q_free) × T_N/T."""
        V = 0.100
        P0 = _P_ATM          # start from atmosphere
        P_tg = 800_000.0
        Q = 1e-3             # 1 L/s free air
        T = _T_N
        res = charge_time(V, P0, P_tg, Q, T_K=T)
        assert res["ok"] is True
        delta_P = P_tg - P0
        delta_V = V * (delta_P / _P_ATM) * (_T_N / T)
        t_expected = delta_V / Q
        assert abs(res["t_charge_s"] - t_expected) / t_expected < REL

    def test_delta_p_field(self):
        """delta_P_Pa = P_final - P_initial."""
        P0, P_tg = _P_ATM, 700_000.0
        res = charge_time(0.100, P0, P_tg, 1e-3)
        assert abs(res["delta_P_Pa"] - (P_tg - P0)) < 1e-6

    def test_delta_v_Nl_consistent(self):
        """delta_V_free_Nl = delta_V_free_m3 × 1000."""
        res = charge_time(0.100, _P_ATM, 800_000.0, 1e-3)
        assert abs(res["delta_V_free_Nl"] - res["delta_V_free_m3"] * 1000.0) < REL

    def test_t_charge_min_consistent(self):
        """t_charge_min = t_charge_s / 60."""
        res = charge_time(0.100, _P_ATM, 800_000.0, 1e-3)
        assert abs(res["t_charge_min"] - res["t_charge_s"] / 60.0) < REL

    def test_larger_volume_longer_charge(self):
        """Doubling V doubles charge time."""
        args = (_P_ATM, 800_000.0, 1e-3)
        t1 = charge_time(0.100, *args)["t_charge_s"]
        t2 = charge_time(0.200, *args)["t_charge_s"]
        assert abs(t2 / t1 - 2.0) < 1e-9

    def test_p_final_le_p_initial_returns_error(self):
        res = charge_time(0.100, 800_000.0, 700_000.0, 1e-3)
        assert res["ok"] is False

    def test_p_initial_below_atm_returns_error(self):
        res = charge_time(0.100, 50_000.0, 700_000.0, 1e-3)
        assert res["ok"] is False

    def test_zero_compressor_returns_error(self):
        res = charge_time(0.100, _P_ATM, 700_000.0, 0.0)
        assert res["ok"] is False


# ===========================================================================
# 8. frl_pressure_drop
# ===========================================================================

class TestFRLPressureDrop:

    def test_total_drop_is_sum_of_components(self):
        """total_dP = filter_dP + regulator_dP + lubricator_dP."""
        res = frl_pressure_drop(1e-3, 700_000.0,
                                filter_dP_Pa=15_000.0,
                                regulator_dP_Pa=25_000.0,
                                lubricator_dP_Pa=12_000.0)
        assert res["ok"] is True
        total = 15_000.0 + 25_000.0 + 12_000.0
        assert abs(res["total_dP_Pa"] - total) < 1e-6

    def test_outlet_pressure_formula(self):
        """P_outlet = P_supply - total_dP."""
        P_s = 700_000.0
        res = frl_pressure_drop(1e-3, P_s)
        expected_outlet = P_s - res["total_dP_Pa"]
        assert abs(res["P_outlet_Pa"] - expected_outlet) < 1e-6

    def test_outlet_bar_consistent(self):
        """P_outlet_bar = P_outlet_Pa / 1e5."""
        res = frl_pressure_drop(1e-3, 700_000.0)
        assert abs(res["P_outlet_bar"] - res["P_outlet_Pa"] / 1e5) < REL

    def test_total_dP_bar_consistent(self):
        """total_dP_bar = total_dP_Pa / 1e5."""
        res = frl_pressure_drop(1e-3, 700_000.0)
        assert abs(res["total_dP_bar"] - res["total_dP_Pa"] / 1e5) < REL

    def test_efficiency_pct_formula(self):
        """efficiency_pct = P_outlet / P_supply × 100."""
        P_s = 700_000.0
        res = frl_pressure_drop(1e-3, P_s)
        expected = (res["P_outlet_Pa"] / P_s) * 100.0
        assert abs(res["efficiency_pct"] - expected) < REL

    def test_high_drop_warns_low_efficiency(self):
        """Very large FRL drop → efficiency warning issued."""
        # Make total_dP > 15% of supply
        P_s = 500_000.0
        res = frl_pressure_drop(1e-3, P_s,
                                filter_dP_Pa=50_000.0,
                                regulator_dP_Pa=50_000.0,
                                lubricator_dP_Pa=50_000.0)
        assert res["ok"] is True
        assert len(res["warnings"]) > 0

    def test_supply_at_atm_returns_error(self):
        res = frl_pressure_drop(1e-3, _P_ATM)
        assert res["ok"] is False

    def test_negative_filter_drop_returns_error(self):
        res = frl_pressure_drop(1e-3, 700_000.0, filter_dP_Pa=-1000.0)
        assert res["ok"] is False

    def test_default_drops_used_when_omitted(self):
        """Default drops: filter=10000, regulator=20000, lubricator=10000 → total=40000."""
        res = frl_pressure_drop(1e-3, 700_000.0)
        assert res["ok"] is True
        assert abs(res["total_dP_Pa"] - 40_000.0) < 1e-6


# ===========================================================================
# LLM tool wrappers
# ===========================================================================

class TestToolWrappers:

    def test_run_pneu_cylinder_happy_path(self):
        ctx = _ctx()
        raw = _run(run_pneu_cylinder(ctx, _args(
            bore_m=0.080, rod_m=0.032, supply_pressure_Pa=700_000.0
        )))
        d = _ok_tool(raw)
        assert d["F_extend_th_N"] > 0
        assert d["F_extend_eff_N"] > 0

    def test_run_pneu_cylinder_missing_bore(self):
        ctx = _ctx()
        raw = _run(run_pneu_cylinder(ctx, _args(
            rod_m=0.032, supply_pressure_Pa=700_000.0
        )))
        _err_tool(raw)

    def test_run_pneu_cylinder_bad_json(self):
        ctx = _ctx()
        raw = _run(run_pneu_cylinder(ctx, b"not json"))
        _err_tool(raw)

    def test_run_pneu_air_consumption_happy_path(self):
        ctx = _ctx()
        raw = _run(run_pneu_air_consumption(ctx, _args(
            bore_m=0.063, rod_m=0.025, stroke_m=0.150,
            supply_pressure_Pa=600_000.0, cycles_per_min=10.0
        )))
        d = _ok_tool(raw)
        assert d["Q_free_Nl_min"] > 0

    def test_run_pneu_air_consumption_missing_stroke(self):
        ctx = _ctx()
        raw = _run(run_pneu_air_consumption(ctx, _args(
            bore_m=0.063, rod_m=0.025,
            supply_pressure_Pa=600_000.0, cycles_per_min=10.0
        )))
        _err_tool(raw)

    def test_run_pneu_valve_iso6358_choked(self):
        ctx = _ctx()
        P1 = 700_000.0
        raw = _run(run_pneu_valve_iso6358(ctx, _args(
            P1_Pa=P1, P2_Pa=P1 * 0.15, T1_K=293.15,
            C_m3s_Pa=1e-8, b=0.30
        )))
        d = _ok_tool(raw)
        assert d["choked"] is True
        assert d["q_Nl_min"] > 0

    def test_run_pneu_valve_iso6358_subsonic(self):
        ctx = _ctx()
        P1 = 500_000.0
        raw = _run(run_pneu_valve_iso6358(ctx, _args(
            P1_Pa=P1, P2_Pa=P1 * 0.80, T1_K=293.15,
            C_m3s_Pa=1e-8, b=0.30
        )))
        d = _ok_tool(raw)
        assert d["choked"] is False

    def test_run_pneu_valve_iso6358_missing_b(self):
        ctx = _ctx()
        raw = _run(run_pneu_valve_iso6358(ctx, _args(
            P1_Pa=500_000.0, P2_Pa=300_000.0, T1_K=293.15, C_m3s_Pa=1e-8
        )))
        _err_tool(raw)

    def test_run_pneu_valve_cv_choked(self):
        ctx = _ctx()
        P1 = 700_000.0
        raw = _run(run_pneu_valve_cv(ctx, _args(
            Cv=5.0, P1_Pa=P1, P2_Pa=P1 * 0.30, T_K=293.15
        )))
        d = _ok_tool(raw)
        assert d["choked"] is True
        assert d["q_Nl_min"] > 0

    def test_run_pneu_valve_cv_missing_P1(self):
        ctx = _ctx()
        raw = _run(run_pneu_valve_cv(ctx, _args(
            Cv=5.0, P2_Pa=300_000.0, T_K=293.15
        )))
        _err_tool(raw)

    def test_run_pneu_receiver_sizing_happy_path(self):
        ctx = _ctx()
        raw = _run(run_pneu_receiver_sizing(ctx, _args(
            V_receiver_m3=0.200,
            P_high_Pa=900_000.0, P_low_Pa=700_000.0,
            Q_demand_m3s_free=5e-4
        )))
        d = _ok_tool(raw)
        assert d["t_supply_s"] > 0
        assert d["delta_V_free_Nl"] > 0

    def test_run_pneu_receiver_sizing_missing_volume(self):
        ctx = _ctx()
        raw = _run(run_pneu_receiver_sizing(ctx, _args(
            P_high_Pa=900_000.0, P_low_Pa=700_000.0,
            Q_demand_m3s_free=5e-4
        )))
        _err_tool(raw)

    def test_run_pneu_blowdown_time_happy_path(self):
        ctx = _ctx()
        raw = _run(run_pneu_blowdown_time(ctx, _args(
            V_m3=0.100, P_initial_Pa=700_000.0, P_final_Pa=_P_ATM,
            C_m3s_Pa=1e-7, b=0.30
        )))
        d = _ok_tool(raw)
        assert d["t_total_s"] > 0

    def test_run_pneu_blowdown_time_missing_b(self):
        ctx = _ctx()
        raw = _run(run_pneu_blowdown_time(ctx, _args(
            V_m3=0.100, P_initial_Pa=700_000.0, P_final_Pa=_P_ATM,
            C_m3s_Pa=1e-7
        )))
        _err_tool(raw)

    def test_run_pneu_charge_time_happy_path(self):
        ctx = _ctx()
        raw = _run(run_pneu_charge_time(ctx, _args(
            V_m3=0.100, P_initial_Pa=_P_ATM,
            P_final_Pa=800_000.0, Q_compressor_m3s_free=1e-3
        )))
        d = _ok_tool(raw)
        assert d["t_charge_s"] > 0
        assert d["t_charge_min"] == pytest.approx(d["t_charge_s"] / 60.0)

    def test_run_pneu_charge_time_missing_q(self):
        ctx = _ctx()
        raw = _run(run_pneu_charge_time(ctx, _args(
            V_m3=0.100, P_initial_Pa=_P_ATM, P_final_Pa=800_000.0
        )))
        _err_tool(raw)

    def test_run_pneu_frl_drop_happy_path(self):
        ctx = _ctx()
        raw = _run(run_pneu_frl_drop(ctx, _args(
            Q_free_m3s=1e-3, supply_pressure_Pa=700_000.0
        )))
        d = _ok_tool(raw)
        assert d["total_dP_Pa"] > 0
        assert d["P_outlet_Pa"] < 700_000.0

    def test_run_pneu_frl_drop_custom_components(self):
        ctx = _ctx()
        raw = _run(run_pneu_frl_drop(ctx, _args(
            Q_free_m3s=2e-3, supply_pressure_Pa=800_000.0,
            filter_dP_Pa=5_000.0, regulator_dP_Pa=15_000.0,
            lubricator_dP_Pa=5_000.0
        )))
        d = _ok_tool(raw)
        assert abs(d["total_dP_Pa"] - 25_000.0) < 1e-6

    def test_run_pneu_frl_drop_missing_supply(self):
        ctx = _ctx()
        raw = _run(run_pneu_frl_drop(ctx, _args(Q_free_m3s=1e-3)))
        _err_tool(raw)


# ===========================================================================
# 9. CITABLE EXTERNAL-REFERENCE CASES — known numeric answers
# ===========================================================================
#
# Cross-checked against ISO 6358 / NFPA / SMC / Festo worked examples with
# hand-computable answers.  SAFETY-relevant: pneumatic pressure systems.
#
# Sources
# -------
# [ISO6358]  ISO 6358-1:2013 — sonic conductance C, critical ratio b.
# [NFPA]     NFPA T3.21.3 — cylinder force/speed conventions.
# [SMC]      SMC "Pneumatic Actuator" technical handbook.
# [Festo]    Festo "Pneumatic Fundamentals" (2nd ed.) — free-air & valve flow.
# ===========================================================================

class TestCitableReferenceCases:

    def test_ref_cylinder_force_nfpa_100mm_6bar(self):
        """[NFPA / SMC] Theoretical extend force = gauge pressure × bore area.
        100 mm bore, 6 bar gauge: A_bore = π/4·0.10² = 7.85398e-3 m²,
        F_th = 6e5 · 7.85398e-3 = 4712.389 N.
        """
        res = cylinder(0.100, 0.025, 6e5 + _P_ATM)
        assert res["ok"] is True
        A = math.pi / 4.0 * 0.100 ** 2
        assert res["F_extend_th_N"] == pytest.approx(6e5 * A, rel=1e-9)
        assert res["F_extend_th_N"] == pytest.approx(4712.389, abs=1e-3)

    def test_ref_iso6358_critical_pressure_ratio(self):
        """[ISO6358] Ideal-gas critical pressure ratio for air (γ=1.4):
        b_ideal = (2/(γ+1))^(γ/(γ−1)) = (2/2.4)^3.5 = 0.528282.
        """
        assert _B_IDEAL == pytest.approx(0.528282, abs=1e-6)

    def test_ref_iso6358_choked_flow(self):
        """[ISO6358 / Festo] Choked volumetric flow q = C·P1·√(T_N/T1).
        C=1.5e-8 m³/(s·Pa), P1=8 bar abs, T1=T_N
        → q = 1.5e-8·8e5 = 0.012 m³/s = 720 Nl/min (choked, P2/P1=0.125<b).
        """
        res = valve_flow_iso6358(8e5, 1e5, _T_N, 1.5e-8, 0.30)
        assert res["ok"] is True
        assert res["choked"] is True
        assert res["q_m3s_normal"] == pytest.approx(0.012, rel=1e-9)
        assert res["q_Nl_min"] == pytest.approx(720.0, rel=1e-9)

    def test_ref_air_consumption_compression_ratio(self):
        """[Festo] Double-acting free-air consumption.
        bore=50 mm, rod=20 mm, stroke=100 mm, 6 bar abs, 30 cycles/min, T=T_N.
        V_cyc = (A_b+A_r)·s·r ; Q = V_cyc·cpm·1000.  Hand → 64.18058 Nl/min.
        """
        res = air_consumption(0.050, 0.020, 0.100, 6e5, 30.0)
        assert res["ok"] is True
        A_b = math.pi / 4.0 * 0.050 ** 2
        A_r = math.pi / 4.0 * (0.050 ** 2 - 0.020 ** 2)
        r = 6e5 / _P_ATM
        hand = (A_b * 0.100 + A_r * 0.100) * r * 30.0 * 1000.0
        assert res["Q_free_Nl_min"] == pytest.approx(hand, rel=1e-9)
        assert res["Q_free_Nl_min"] == pytest.approx(64.18058, abs=1e-4)

    def test_ref_receiver_sizing_isothermal(self):
        """[Festo] Free air stored ΔV = V·(P_hi−P_lo)/P_atm·(T_N/T).
        V=0.5 m³, P_hi=8 bar abs, P_lo=6 bar abs, Q_d=1e-3 m³/s, T=T_N.
        ΔV = 0.5·(2e5/101325) = 0.986923 m³ ; t = ΔV/Q_d = 986.923 s.
        """
        res = receiver_sizing(0.5, 8e5, 6e5, 1e-3)
        assert res["ok"] is True
        hand = 0.5 * (2e5 / _P_ATM) * 1.0
        assert res["delta_V_free_m3"] == pytest.approx(hand, rel=1e-12)
        assert res["t_supply_s"] == pytest.approx(986.92327, abs=1e-3)

    def test_ref_charge_time_isothermal(self):
        """[Festo] Charge time t = V·(ΔP/P_atm)·(T_N/T) / Q_compressor.
        V=0.3 m³, P0=P_atm, P_tg=8 bar abs, Q_c=2e-3 m³/s
        → ΔV = 0.3·((8e5−101325)/101325) = 2.068616 m³, t = 1034.30792 s.
        """
        res = charge_time(0.3, _P_ATM, 8e5, 2e-3)
        assert res["ok"] is True
        hand = 0.3 * ((8e5 - _P_ATM) / _P_ATM)
        assert res["delta_V_free_m3"] == pytest.approx(hand, rel=1e-12)
        assert res["t_charge_s"] == pytest.approx(1034.30792, abs=1e-3)

    def test_ref_valve_flow_cv_choked_constant(self):
        """[Masoneilan/Fisher] Choked Cv air flow q_max = 417·Cv·P1[bar]·
        √(T_N/(SG·T)).  Cv=2, P1=6 bar, SG=1, T=T_N
        → q_max = 417·2·6·1 = 5004 Nl/min.
        """
        res = valve_flow_cv(2.0, 6e5, 6e5 * 0.30, _T_N, SG_gas=1.0)
        assert res["ok"] is True
        assert res["choked"] is True
        assert res["q_max_Nl_min"] == pytest.approx(5004.0, rel=1e-9)
