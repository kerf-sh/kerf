"""
Hermetic tests for kerf_electronics.gatedrive — gate-driver & switching-loss design.

Covers ≥30 tests vs power-electronics hand-calcs:

  gate_drive_power
    - P_drive = Qg × fsw × Vgs hand-calc
    - Ig_avg = Qg × fsw hand-calc
    - negative turn-off bias: vgs_swing = Vdrive − Voff
    - Vdrive <= Voff → ok=False

  gate_resistor_design
    - Rg_total = Vgs_swing × t_trans / Qg hand-calc
    - Ipeak = Vgs_swing / Rg_total hand-calc
    - Rg_ext = Rg_total − Rg_internal hand-calc
    - Rg_ext floored at 0 when Rg_int >= Rg_total
    - negative vgs_off respected in swing calc
    - invalid t_transition → ok=False

  miller_spurious_turnon
    - dvdt_critical = (Vth − Voff) / (Cgd × Rg_off) hand-calc
    - spurious_risk=False when dvdt_bus < dvdt_critical
    - spurious_risk=True when dvdt_bus >= dvdt_critical (with warning)
    - margin_ratio = dvdt_critical / dvdt_bus hand-calc
    - vgs_off >= vgs_th → ok=False

  switching_loss
    - Eon = 0.5 × Vbus × Iload × ton hand-calc
    - Eoff = 0.5 × Vbus × Iload × toff hand-calc
    - Psw = (Eon + Eoff) × fsw hand-calc
    - Rg scaling: Eon scales linearly with Rg_actual / Rg_ref
    - zero Vbus → ok=False

  conduction_loss
    - MOSFET: P = Rds × Irms² hand-calc
    - IGBT with i_avg: P = Vce × I_avg hand-calc
    - IGBT simplified: P ≈ Vce × Irms × duty hand-calc
    - unknown device_type → ok=False
    - mosfet without rds_on → ok=False

  diode_recovery_loss
    - P_rr = Qrr × Vbus × fsw hand-calc
    - E_rr = Qrr × Vbus hand-calc
    - zero Qrr → ok=False

  total_loss_and_thermal
    - Tj = T_amb + P × (Rjc + Rcs + Rsa) hand-calc
    - over_temp=True when Tj > Tj_max (with warning)
    - t_margin = Tj_max − Tj hand-calc
    - Rth_sa_required = (Tj_max − T_amb)/P − Rjc − Rcs hand-calc
    - SOA exceeded when Vds_stress > 0.8 × Vds_rated (warning)

  dead_time_select
    - t_dead_min = Coss × Vbus / I_drive hand-calc
    - shoot_through_risk=True when t_dead < t_dead_min (warning)
    - excessive_body_diode=True when t_dead > t_body_diode_max (warning)
    - no t_dead_s → shoot_through_risk absent from result

  bootstrap_cap_sizing
    - C_boot = (Qg + I_bias×T) / ΔV hand-calc (no leakage, n=1)
    - n_cycles=3 scales Q_gate by 3 hand-calc
    - leakage adds to Q_total hand-calc
    - zero dv_max → ok=False
"""
from __future__ import annotations

import math
import warnings

import pytest

from kerf_electronics.gatedrive.drive import (
    gate_drive_power,
    gate_resistor_design,
    miller_spurious_turnon,
    switching_loss,
    conduction_loss,
    diode_recovery_loss,
    total_loss_and_thermal,
    dead_time_select,
    bootstrap_cap_sizing,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _rel(a: float, b: float, tol: float = 1e-6) -> bool:
    """Relative-error check; tolerates b == 0 via absolute check."""
    if b == 0:
        return abs(a) < tol
    return abs(a - b) / abs(b) < tol


# ═══════════════════════════════════════════════════════════════════════════════
# gate_drive_power
# ═══════════════════════════════════════════════════════════════════════════════

class TestGateDrivePower:
    def test_p_drive_basic(self):
        # P_drive = Qg × fsw × Vgs_swing = 100e-9 × 100e3 × 12 = 0.12 W
        r = gate_drive_power(qg_c=100e-9, fsw_hz=100e3, vgs_drive_v=12.0)
        assert r["ok"]
        assert _rel(r["p_drive_w"], 100e-9 * 100e3 * 12.0)

    def test_ig_avg(self):
        # Ig_avg = Qg × fsw = 50e-9 × 200e3 = 0.01 A
        r = gate_drive_power(qg_c=50e-9, fsw_hz=200e3, vgs_drive_v=15.0)
        assert r["ok"]
        assert _rel(r["ig_avg_a"], 50e-9 * 200e3)

    def test_vgs_swing_default_zero_off(self):
        r = gate_drive_power(qg_c=80e-9, fsw_hz=50e3, vgs_drive_v=12.0, vgs_off_v=0.0)
        assert r["ok"]
        assert _rel(r["vgs_swing_v"], 12.0)

    def test_negative_gate_bias_swing(self):
        # vgs_swing = 15 − (−5) = 20 V
        r = gate_drive_power(qg_c=100e-9, fsw_hz=100e3, vgs_drive_v=15.0, vgs_off_v=-5.0)
        assert r["ok"]
        assert _rel(r["vgs_swing_v"], 20.0)
        assert _rel(r["p_drive_w"], 100e-9 * 100e3 * 20.0)
        # negative bias note should be present
        assert len(r["note"]) > 0

    def test_vdrive_le_voff_error(self):
        r = gate_drive_power(qg_c=100e-9, fsw_hz=100e3, vgs_drive_v=5.0, vgs_off_v=5.0)
        assert not r["ok"]

    def test_negative_qg_error(self):
        r = gate_drive_power(qg_c=-1e-9, fsw_hz=100e3, vgs_drive_v=12.0)
        assert not r["ok"]


# ═══════════════════════════════════════════════════════════════════════════════
# gate_resistor_design
# ═══════════════════════════════════════════════════════════════════════════════

class TestGateResistorDesign:
    def test_rg_total_hand_calc(self):
        # Rg = Vswing × t / Qg = 12 × 50e-9 / 100e-9 = 6 Ω
        r = gate_resistor_design(
            vgs_drive_v=12.0, qg_c=100e-9, t_transition_s=50e-9
        )
        assert r["ok"]
        assert _rel(r["rg_total_ohm"], 6.0)

    def test_ipeak(self):
        # Ipeak = Vswing / Rg_total = 12 / 6 = 2 A
        r = gate_resistor_design(
            vgs_drive_v=12.0, qg_c=100e-9, t_transition_s=50e-9
        )
        assert r["ok"]
        assert _rel(r["ipeak_a"], 2.0)

    def test_rg_ext_subtraction(self):
        # Rg_total = 6 Ω, Rg_int = 2 Ω → Rg_ext = 4 Ω
        r = gate_resistor_design(
            vgs_drive_v=12.0, qg_c=100e-9, t_transition_s=50e-9,
            rg_internal_ohm=2.0
        )
        assert r["ok"]
        assert _rel(r["rg_ext_ohm"], 4.0)

    def test_rg_ext_clamped_to_zero(self):
        # Rg_total = 6 Ω, Rg_int = 10 Ω → Rg_ext = 0
        r = gate_resistor_design(
            vgs_drive_v=12.0, qg_c=100e-9, t_transition_s=50e-9,
            rg_internal_ohm=10.0
        )
        assert r["ok"]
        assert r["rg_ext_ohm"] == 0.0

    def test_negative_off_bias_in_swing(self):
        # vgs_swing = 15 − (−5) = 20 V; Rg = 20 × 50e-9 / 100e-9 = 10 Ω
        r = gate_resistor_design(
            vgs_drive_v=15.0, qg_c=100e-9, t_transition_s=50e-9, vgs_off_v=-5.0
        )
        assert r["ok"]
        assert _rel(r["rg_total_ohm"], 10.0)

    def test_zero_transition_time_error(self):
        r = gate_resistor_design(vgs_drive_v=12.0, qg_c=100e-9, t_transition_s=0)
        assert not r["ok"]


# ═══════════════════════════════════════════════════════════════════════════════
# miller_spurious_turnon
# ═══════════════════════════════════════════════════════════════════════════════

class TestMillerSpuriousTurnon:
    def test_dvdt_critical_hand_calc(self):
        # dvdt_crit = (Vth − Voff) / (Cgd × Rg_off)
        # = (4 − 0) / (1e-9 × 10) = 4 / 10e-9 = 4e8 V/s
        r = miller_spurious_turnon(
            cgd_f=1e-9, vgs_th_v=4.0, rg_off_ohm=10.0, vbus_v=400.0
        )
        assert r["ok"]
        assert _rel(r["dvdt_critical_vps"], 4e8)

    def test_no_spurious_when_dvdt_bus_below_crit(self):
        # dvdt_crit = 4e8 V/s; dvdt_bus = 400 / 10e-6 = 4e7 V/s < crit
        r = miller_spurious_turnon(
            cgd_f=1e-9, vgs_th_v=4.0, rg_off_ohm=10.0,
            vbus_v=400.0, t_rise_s=10e-6
        )
        assert r["ok"]
        assert r["spurious_risk"] is False

    def test_spurious_risk_when_dvdt_bus_exceeds_crit(self):
        # dvdt_crit = 4e8; dvdt_bus = 400 / 100e-9 = 4e9 > crit
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            r = miller_spurious_turnon(
                cgd_f=1e-9, vgs_th_v=4.0, rg_off_ohm=10.0,
                vbus_v=400.0, t_rise_s=100e-9
            )
        assert r["ok"]
        assert r["spurious_risk"] is True
        assert any("SHOOT-THROUGH" in str(x.message) for x in w)

    def test_margin_ratio_hand_calc(self):
        # dvdt_crit = 4e8, dvdt_bus = 400/10e-6 = 4e7
        # margin_ratio = 4e8 / 4e7 = 10
        r = miller_spurious_turnon(
            cgd_f=1e-9, vgs_th_v=4.0, rg_off_ohm=10.0,
            vbus_v=400.0, t_rise_s=10e-6
        )
        assert r["ok"]
        assert _rel(r["margin_ratio"], 10.0, tol=1e-4)

    def test_negative_bias_increases_margin(self):
        # dvdt_crit = (4 − (−5)) / (1e-9 × 10) = 9e8 V/s
        r = miller_spurious_turnon(
            cgd_f=1e-9, vgs_th_v=4.0, rg_off_ohm=10.0,
            vbus_v=400.0, vgs_off_v=-5.0
        )
        assert r["ok"]
        assert _rel(r["dvdt_critical_vps"], 9e8)

    def test_vgs_off_eq_vgs_th_error(self):
        r = miller_spurious_turnon(
            cgd_f=1e-9, vgs_th_v=4.0, rg_off_ohm=10.0,
            vbus_v=400.0, vgs_off_v=4.0
        )
        assert not r["ok"]


# ═══════════════════════════════════════════════════════════════════════════════
# switching_loss
# ═══════════════════════════════════════════════════════════════════════════════

class TestSwitchingLoss:
    def test_eon_hand_calc(self):
        # Eon = 0.5 × 400 × 10 × 50e-9 = 100e-6 J
        r = switching_loss(
            vbus_v=400.0, i_load_a=10.0, t_on_s=50e-9, t_off_s=80e-9, fsw_hz=100e3
        )
        assert r["ok"]
        assert _rel(r["eon_j"], 0.5 * 400.0 * 10.0 * 50e-9)

    def test_eoff_hand_calc(self):
        r = switching_loss(
            vbus_v=400.0, i_load_a=10.0, t_on_s=50e-9, t_off_s=80e-9, fsw_hz=100e3
        )
        assert r["ok"]
        assert _rel(r["eoff_j"], 0.5 * 400.0 * 10.0 * 80e-9)

    def test_psw_hand_calc(self):
        # Psw = (Eon + Eoff) × fsw
        r = switching_loss(
            vbus_v=400.0, i_load_a=10.0, t_on_s=50e-9, t_off_s=80e-9, fsw_hz=100e3
        )
        assert r["ok"]
        eon = 0.5 * 400.0 * 10.0 * 50e-9
        eoff = 0.5 * 400.0 * 10.0 * 80e-9
        assert _rel(r["psw_w"], (eon + eoff) * 100e3)

    def test_rg_scaling(self):
        # Reference at Rg_ref=10Ω; actual Rg=20Ω → times scale by 2
        r_ref = switching_loss(
            vbus_v=400.0, i_load_a=10.0, t_on_s=50e-9, t_off_s=80e-9, fsw_hz=100e3
        )
        r_scaled = switching_loss(
            vbus_v=400.0, i_load_a=10.0, t_on_s=50e-9, t_off_s=80e-9, fsw_hz=100e3,
            rg_actual_ohm=20.0, rg_ref_ohm=10.0
        )
        assert r_scaled["ok"]
        assert _rel(r_scaled["eon_j"], r_ref["eon_j"] * 2.0)
        assert r_scaled["rg_scaling_applied"] is True

    def test_rg_scale_unity(self):
        r = switching_loss(
            vbus_v=400.0, i_load_a=10.0, t_on_s=50e-9, t_off_s=80e-9, fsw_hz=100e3,
            rg_actual_ohm=10.0, rg_ref_ohm=10.0
        )
        assert r["ok"]
        assert _rel(r["rg_scale"], 1.0)

    def test_zero_vbus_error(self):
        r = switching_loss(
            vbus_v=0.0, i_load_a=10.0, t_on_s=50e-9, t_off_s=80e-9, fsw_hz=100e3
        )
        assert not r["ok"]


# ═══════════════════════════════════════════════════════════════════════════════
# conduction_loss
# ═══════════════════════════════════════════════════════════════════════════════

class TestConductionLoss:
    def test_mosfet_hand_calc(self):
        # P = 0.020 × 5² = 0.5 W
        r = conduction_loss(device_type="mosfet", i_rms_a=5.0, rds_on_ohm=0.020)
        assert r["ok"]
        assert _rel(r["p_cond_w"], 0.020 * 5.0 ** 2)

    def test_igbt_with_i_avg(self):
        # P = 1.8 × 3.0 = 5.4 W
        r = conduction_loss(
            device_type="igbt", i_rms_a=5.0, vce_sat_v=1.8, i_avg_a=3.0
        )
        assert r["ok"]
        assert _rel(r["p_cond_w"], 1.8 * 3.0)

    def test_igbt_simplified_duty(self):
        # P ≈ Vce × Irms × duty = 2.0 × 10.0 × 0.5 = 10.0 W
        r = conduction_loss(
            device_type="igbt", i_rms_a=10.0, vce_sat_v=2.0, duty=0.5
        )
        assert r["ok"]
        assert _rel(r["p_cond_w"], 2.0 * 10.0 * 0.5)

    def test_unknown_device_type_error(self):
        r = conduction_loss(device_type="bjt", i_rms_a=5.0, rds_on_ohm=0.01)
        assert not r["ok"]

    def test_mosfet_missing_rds_error(self):
        r = conduction_loss(device_type="mosfet", i_rms_a=5.0)
        assert not r["ok"]

    def test_igbt_missing_vce_error(self):
        r = conduction_loss(device_type="igbt", i_rms_a=5.0)
        assert not r["ok"]


# ═══════════════════════════════════════════════════════════════════════════════
# diode_recovery_loss
# ═══════════════════════════════════════════════════════════════════════════════

class TestDiodeRecoveryLoss:
    def test_p_rr_hand_calc(self):
        # P_rr = 200e-9 × 400 × 100e3 = 8.0 W
        r = diode_recovery_loss(qrr_c=200e-9, vbus_v=400.0, fsw_hz=100e3)
        assert r["ok"]
        assert _rel(r["p_rr_w"], 200e-9 * 400.0 * 100e3)

    def test_e_rr_hand_calc(self):
        # E_rr = Qrr × Vbus = 200e-9 × 400 = 80 µJ
        r = diode_recovery_loss(qrr_c=200e-9, vbus_v=400.0, fsw_hz=100e3)
        assert r["ok"]
        assert _rel(r["e_rr_j"], 200e-9 * 400.0)

    def test_zero_qrr_error(self):
        r = diode_recovery_loss(qrr_c=0.0, vbus_v=400.0, fsw_hz=100e3)
        assert not r["ok"]

    def test_result_keys(self):
        r = diode_recovery_loss(qrr_c=50e-9, vbus_v=200.0, fsw_hz=50e3)
        assert r["ok"]
        for k in ("p_rr_w", "e_rr_j", "qrr_c", "vbus_v", "fsw_hz"):
            assert k in r


# ═══════════════════════════════════════════════════════════════════════════════
# total_loss_and_thermal
# ═══════════════════════════════════════════════════════════════════════════════

class TestTotalLossAndThermal:
    def test_tj_hand_calc(self):
        # P = 5+3+0.5+1 = 9.5 W; Rth = 0.5+0.1+2 = 2.6 °C/W; Tj = 25 + 9.5×2.6 = 49.7 °C
        r = total_loss_and_thermal(
            p_sw_w=5.0, p_cond_w=3.0, p_drive_w=0.5, p_rr_w=1.0,
            t_amb_c=25.0, r_th_jc=0.5, r_th_cs=0.1, r_th_sa=2.0,
            tj_max_c=150.0
        )
        assert r["ok"]
        assert _rel(r["tj_c"], 25.0 + 9.5 * 2.6, tol=1e-4)

    def test_over_temp_flag(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            r = total_loss_and_thermal(
                p_sw_w=50.0, p_cond_w=50.0,
                t_amb_c=25.0, r_th_jc=1.0, r_th_cs=0.2, r_th_sa=0.5,
                tj_max_c=150.0
            )
        assert r["ok"]
        assert r["over_temp"] is True
        assert any("OVER-TEMPERATURE" in str(x.message) for x in w)

    def test_t_margin_hand_calc(self):
        r = total_loss_and_thermal(
            p_sw_w=5.0, p_cond_w=3.0,
            t_amb_c=25.0, r_th_jc=0.5, r_th_cs=0.1, r_th_sa=2.0,
            tj_max_c=150.0
        )
        assert r["ok"]
        tj = 25.0 + 8.0 * 2.6
        assert _rel(r["t_margin_c"], 150.0 - tj, tol=1e-4)

    def test_rth_sa_required(self):
        # P = 10, T_amb = 25, Tj_max = 125; Rjc=0.5, Rcs=0.1
        # Rsa_req = (125−25)/10 − 0.5 − 0.1 = 10 − 0.6 = 9.4 °C/W
        r = total_loss_and_thermal(
            p_sw_w=6.0, p_cond_w=4.0,
            t_amb_c=25.0, r_th_jc=0.5, r_th_cs=0.1, r_th_sa=0.0,
            tj_max_c=125.0
        )
        assert r["ok"]
        assert _rel(r["r_th_sa_required"], 9.4, tol=1e-4)

    def test_soa_exceeded_warning(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            r = total_loss_and_thermal(
                p_sw_w=2.0, p_cond_w=2.0,
                t_amb_c=25.0, r_th_jc=1.0, r_th_sa=5.0,
                tj_max_c=150.0,
                vds_stress_v=450.0, vds_rated_v=500.0  # 450/500 = 90% > 80%
            )
        assert r["ok"]
        assert r["soa_ok"] is False
        assert any("SOA" in str(x.message) for x in w)

    def test_soa_ok_within_derating(self):
        r = total_loss_and_thermal(
            p_sw_w=2.0, p_cond_w=2.0,
            t_amb_c=25.0, r_th_jc=1.0, r_th_sa=5.0,
            tj_max_c=150.0,
            vds_stress_v=350.0, vds_rated_v=600.0  # 350/600 ≈ 58% < 80%
        )
        assert r["ok"]
        assert r["soa_ok"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# dead_time_select
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeadTimeSelect:
    def test_t_dead_min_hand_calc(self):
        # t_dead_min = Coss × Vbus / I_drive = 1e-9 × 400 / 2 = 200 ns
        r = dead_time_select(coss_f=1e-9, vbus_v=400.0, i_drive_a=2.0)
        assert r["ok"]
        assert _rel(r["t_dead_min_s"], 200e-9)

    def test_shoot_through_risk_true(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            r = dead_time_select(
                coss_f=1e-9, vbus_v=400.0, i_drive_a=2.0,
                t_dead_s=100e-9  # < 200 ns
            )
        assert r["ok"]
        assert r["shoot_through_risk"] is True
        assert any("SHOOT-THROUGH" in str(x.message) for x in w)

    def test_shoot_through_risk_false(self):
        r = dead_time_select(
            coss_f=1e-9, vbus_v=400.0, i_drive_a=2.0,
            t_dead_s=300e-9  # > 200 ns
        )
        assert r["ok"]
        assert r["shoot_through_risk"] is False

    def test_excessive_body_diode(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            r = dead_time_select(
                coss_f=1e-9, vbus_v=400.0, i_drive_a=2.0,
                t_dead_s=1e-6,  # 1 µs > 500 ns default
                t_body_diode_max_s=500e-9
            )
        assert r["ok"]
        assert r["excessive_body_diode"] is True

    def test_no_t_dead_no_risk_keys(self):
        r = dead_time_select(coss_f=1e-9, vbus_v=400.0, i_drive_a=2.0)
        assert r["ok"]
        assert "shoot_through_risk" not in r


# ═══════════════════════════════════════════════════════════════════════════════
# bootstrap_cap_sizing
# ═══════════════════════════════════════════════════════════════════════════════

class TestBootstrapCapSizing:
    def test_c_boot_hand_calc_no_leakage(self):
        # n=1, fsw=100e3, T=10µs
        # Q_gate = 100e-9; Q_bias = 5e-3 × 10e-6 = 50e-9
        # Q_total = 150e-9; C = 150e-9 / 1.0 = 150 nF
        r = bootstrap_cap_sizing(
            qg_c=100e-9, i_bias_a=5e-3, fsw_hz=100e3, dv_max_v=1.0, n_cycles=1
        )
        assert r["ok"]
        q_total = 100e-9 + 5e-3 * (1 / 100e3)
        assert _rel(r["c_boot_f"], q_total / 1.0)

    def test_n_cycles_scales_q_gate(self):
        # n=3: Q_gate = 3 × 100e-9 = 300e-9
        # Use a small but positive i_bias_a; leakage 0 via i_leakage_a=0
        r3 = bootstrap_cap_sizing(
            qg_c=100e-9, i_bias_a=1e-6, fsw_hz=100e3, dv_max_v=1.0, n_cycles=3,
            i_leakage_a=0.0
        )
        r1 = bootstrap_cap_sizing(
            qg_c=100e-9, i_bias_a=1e-6, fsw_hz=100e3, dv_max_v=1.0, n_cycles=1,
            i_leakage_a=0.0
        )
        assert r3["ok"] and r1["ok"]
        assert _rel(r3["q_gate_c"], 3 * r1["q_gate_c"])

    def test_leakage_adds_to_q_total(self):
        r_no_leak = bootstrap_cap_sizing(
            qg_c=100e-9, i_bias_a=1e-3, fsw_hz=100e3, dv_max_v=1.0,
            i_leakage_a=0.0
        )
        r_leak = bootstrap_cap_sizing(
            qg_c=100e-9, i_bias_a=1e-3, fsw_hz=100e3, dv_max_v=1.0,
            i_leakage_a=1e-3
        )
        assert r_no_leak["ok"] and r_leak["ok"]
        assert r_leak["q_total_c"] > r_no_leak["q_total_c"]

    def test_zero_dv_max_error(self):
        r = bootstrap_cap_sizing(
            qg_c=100e-9, i_bias_a=5e-3, fsw_hz=100e3, dv_max_v=0.0
        )
        assert not r["ok"]

    def test_result_keys_present(self):
        r = bootstrap_cap_sizing(
            qg_c=100e-9, i_bias_a=5e-3, fsw_hz=100e3, dv_max_v=0.5
        )
        assert r["ok"]
        for k in ("c_boot_f", "q_total_c", "q_gate_c", "q_bias_c", "n_cycles"):
            assert k in r
