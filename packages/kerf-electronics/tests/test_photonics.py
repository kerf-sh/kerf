"""
Hermetic tests for the photonics optoelectronics module.

Covers ≥30 tests verifying:
  wavelength_to_photon_energy
  led_liv (LED/laser L-I-V, WPE, EQE, thermal droop)
  laser_threshold
  photodiode_responsivity
  photodiode_photocurrent
  photodiode_noise (shot, dark, Johnson, SNR, NEP, D*)
  photodiode_bandwidth (RC, transit-time)
  tia_design (gain, noise, Cf, bandwidth)
  optocoupler (CTR, I_out, V_out, bandwidth scaling)
  fiber_coupling_efficiency
  solar_cell_iv (single-diode, FF, η)
  tof_lidar (range, P_rx, SNR)
  LLM tool handlers (async, stub registry, invalid-JSON path)

Physical constants used in hand-calcs
--------------------------------------
h  = 6.62607015e-34  J·s
c  = 2.99792458e8   m/s
q  = 1.602176634e-19 C
kB = 1.380649e-23   J/K

Author: imranparuk
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
import types
import warnings

# ── Prefer the real kerf_chat if installed; stub otherwise ───────────────────
try:
    import kerf_chat as _kc_pkg  # noqa: F401
    import kerf_chat.tools as _kc_tools  # noqa: F401
    import kerf_chat.tools.registry as _kc_real  # noqa: F401
except Exception:
    _kc_real = None

_reg_stub = types.ModuleType("kerf_chat.tools.registry")
_reg_stub.Registry = type("Registry", (list,), {})
_reg_stub.ToolSpec = type(
    "ToolSpec", (), {"__init__": lambda s, **kw: s.__dict__.update(kw)}
)
_reg_stub.err_payload = lambda msg, code: json.dumps(
    {"ok": False, "error": msg, "code": code}
)
_reg_stub.ok_payload = lambda v: json.dumps({"ok": True, **v})
_reg_stub.register = lambda spec, write=False: (lambda fn: fn)

_kerf_chat_stub = types.ModuleType("kerf_chat")
_kerf_chat_tools_stub = types.ModuleType("kerf_chat.tools")
sys.modules.setdefault("kerf_chat", _kerf_chat_stub)
sys.modules.setdefault("kerf_chat.tools", _kerf_chat_tools_stub)
if _kc_real is None:
    sys.modules["kerf_chat.tools.registry"] = _reg_stub

# ── Ensure src/ is on path ────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest

from kerf_electronics.photonics.devices import (
    fiber_coupling_efficiency,
    laser_threshold,
    led_liv,
    optocoupler,
    photodiode_bandwidth,
    photodiode_noise,
    photodiode_photocurrent,
    photodiode_responsivity,
    solar_cell_iv,
    tia_design,
    tof_lidar,
    wavelength_to_photon_energy,
)

# ── Physical constants ────────────────────────────────────────────────────────

_H  = 6.62607015e-34
_C  = 2.99792458e8
_Q  = 1.602176634e-19
_KB = 1.380649e-23

# ── Load tool module via importlib so stub is active ─────────────────────────
_tool_spec = importlib.util.spec_from_file_location(
    "kerf_electronics.photonics.tools",
    os.path.join(_SRC, "kerf_electronics", "photonics", "tools.py"),
)
_tool_mod = importlib.util.module_from_spec(_tool_spec)
_tool_spec.loader.exec_module(_tool_mod)

tool_wavelength_to_energy   = _tool_mod.photonics_wavelength_to_energy
tool_led_liv                = _tool_mod.photonics_led_liv
tool_laser_threshold        = _tool_mod.photonics_laser_threshold
tool_pd_responsivity        = _tool_mod.photonics_photodiode_responsivity
tool_pd_photocurrent        = _tool_mod.photonics_photodiode_photocurrent
tool_pd_noise               = _tool_mod.photonics_photodiode_noise
tool_pd_bandwidth           = _tool_mod.photonics_photodiode_bandwidth
tool_tia_design             = _tool_mod.photonics_tia_design
tool_optocoupler            = _tool_mod.photonics_optocoupler
tool_fiber_coupling         = _tool_mod.photonics_fiber_coupling
tool_solar_cell_iv          = _tool_mod.photonics_solar_cell_iv
tool_tof_lidar              = _tool_mod.photonics_tof_lidar


async def call(fn, **kwargs):
    result = await fn(None, json.dumps(kwargs).encode())
    return json.loads(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. wavelength_to_photon_energy
# ═══════════════════════════════════════════════════════════════════════════════

class TestWavelengthToPhotonEnergy:
    """E = h·c/λ"""

    def test_1550nm_photon_energy_ev(self):
        """At 1550 nm: E_photon = h·c/λ / q ≈ 0.8 eV."""
        res = wavelength_to_photon_energy(1550e-9)
        assert res["ok"] is True
        expected_ev = _H * _C / (1550e-9 * _Q)
        assert abs(res["photon_energy_ev"] - expected_ev) < 1e-4

    def test_850nm_higher_energy_than_1550nm(self):
        """Shorter wavelength → higher photon energy."""
        e850 = wavelength_to_photon_energy(850e-9)["photon_energy_ev"]
        e1550 = wavelength_to_photon_energy(1550e-9)["photon_energy_ev"]
        assert e850 > e1550

    def test_wavelength_nm_field(self):
        """wavelength_nm = wavelength_m × 1e9."""
        res = wavelength_to_photon_energy(1310e-9)
        assert abs(res["wavelength_nm"] - 1310.0) < 0.01

    def test_freq_hz_consistent(self):
        """freq_hz = c / wavelength_m."""
        lam = 633e-9  # HeNe red
        res = wavelength_to_photon_energy(lam)
        expected_f = _C / lam
        assert abs(res["freq_hz"] - expected_f) / expected_f < 1e-9

    def test_zero_wavelength_returns_error(self):
        res = wavelength_to_photon_energy(0.0)
        assert res["ok"] is False

    def test_negative_wavelength_returns_error(self):
        res = wavelength_to_photon_energy(-500e-9)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 2. led_liv
# ═══════════════════════════════════════════════════════════════════════════════

class TestLedLiv:
    """LED L-I-V, WPE, EQE, thermal droop."""

    def test_above_threshold_has_optical_output(self):
        res = led_liv(
            current_a=0.02, wavelength_m=850e-9,
            slope_efficiency_w_per_a=0.5, threshold_current_a=0.01, vf_v=1.8
        )
        assert res["ok"] is True
        assert res["p_opt_w"] > 0

    def test_below_threshold_zero_output_and_warning(self):
        """I ≤ I_th → p_opt = 0, warning issued."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = led_liv(
                current_a=0.005, wavelength_m=850e-9,
                slope_efficiency_w_per_a=0.5, threshold_current_a=0.01, vf_v=1.8
            )
            assert res["ok"] is True
            assert res["p_opt_w"] == 0.0
            assert res["below_threshold"] is True
            assert len(w) > 0

    def test_p_opt_formula(self):
        """P_opt = slope_eff × (I − I_th)."""
        I = 0.05
        Ith = 0.01
        slope = 0.5
        res = led_liv(
            current_a=I, wavelength_m=850e-9,
            slope_efficiency_w_per_a=slope, threshold_current_a=Ith, vf_v=2.0
        )
        expected = slope * (I - Ith)
        assert abs(res["p_opt_w"] - expected) < 1e-12

    def test_wpe_definition(self):
        """WPE = P_opt / (Vj × I)."""
        res = led_liv(
            current_a=0.03, wavelength_m=850e-9,
            slope_efficiency_w_per_a=0.4, threshold_current_a=0.005, vf_v=1.9,
            series_resistance_ohm=2.0
        )
        vj = res["vj_v"]
        expected_wpe = res["p_opt_w"] / (vj * 0.03)
        assert abs(res["wpe"] - expected_wpe) < 1e-6

    def test_eqe_derived_from_slope(self):
        """EQE = slope_eff × q / (h·f)."""
        lam = 850e-9
        slope = 0.5
        res = led_liv(
            current_a=0.05, wavelength_m=lam,
            slope_efficiency_w_per_a=slope, threshold_current_a=0.0, vf_v=2.0
        )
        freq = _C / lam
        e_photon = _H * freq
        expected_eqe = min(slope * _Q / e_photon, 1.0)
        assert abs(res["eqe"] - expected_eqe) < 1e-4

    def test_thermal_droop_reduces_p_opt(self):
        """Thermal droop > 0 reduces optical power."""
        res = led_liv(
            current_a=0.05, wavelength_m=850e-9,
            slope_efficiency_w_per_a=0.5, threshold_current_a=0.01, vf_v=2.0,
            thermal_droop_per_k=0.005, delta_temp_k=20.0
        )
        assert res["ok"] is True
        assert res["p_opt_thermal_w"] < res["p_opt_w"]

    def test_wavelength_shift_increases_with_temp(self):
        """Red-shift: wavelength_shifted_nm > wavelength_nm for positive shift."""
        res = led_liv(
            current_a=0.05, wavelength_m=850e-9,
            slope_efficiency_w_per_a=0.5, threshold_current_a=0.01, vf_v=2.0,
            wavelength_shift_nm_per_k=0.3, delta_temp_k=25.0
        )
        assert res["ok"] is True
        assert res["wavelength_shifted_nm"] > res["wavelength_nm"]

    def test_invalid_current_returns_error(self):
        res = led_liv(
            current_a=0.0, wavelength_m=850e-9,
            slope_efficiency_w_per_a=0.5, threshold_current_a=0.0, vf_v=2.0
        )
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 3. laser_threshold
# ═══════════════════════════════════════════════════════════════════════════════

class TestLaserThreshold:
    def test_above_threshold_p_opt(self):
        res = laser_threshold(
            current_a=0.05, threshold_current_a=0.02, slope_efficiency_w_per_a=0.3
        )
        assert res["ok"] is True
        assert res["above_threshold"] is True
        expected = 0.3 * (0.05 - 0.02)
        assert abs(res["p_opt_w"] - expected) < 1e-12

    def test_below_threshold_zero_output_warning(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = laser_threshold(
                current_a=0.01, threshold_current_a=0.02, slope_efficiency_w_per_a=0.3
            )
            assert res["ok"] is True
            assert res["p_opt_w"] == 0.0
            assert res["above_threshold"] is False
            assert len(w) > 0

    def test_invalid_threshold_returns_error(self):
        res = laser_threshold(
            current_a=0.05, threshold_current_a=0.0, slope_efficiency_w_per_a=0.3
        )
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 4. photodiode_responsivity
# ═══════════════════════════════════════════════════════════════════════════════

class TestPhotodiodeResponsivity:
    """R = EQE × q × λ / (h × c)"""

    def test_1550nm_qe_80_responsivity(self):
        """At 1550 nm with QE=0.8: R = 0.8 × q × 1550e-9 / (h × c)."""
        lam = 1550e-9
        qe = 0.8
        res = photodiode_responsivity(wavelength_m=lam, quantum_efficiency=qe)
        assert res["ok"] is True
        expected_r = qe * _Q * lam / (_H * _C)
        assert abs(res["responsivity_a_per_w"] - expected_r) / expected_r < 1e-6

    def test_responsivity_proportional_to_wavelength(self):
        """Longer wavelength → higher responsivity (same QE)."""
        r1 = photodiode_responsivity(wavelength_m=850e-9, quantum_efficiency=0.9)
        r2 = photodiode_responsivity(wavelength_m=1310e-9, quantum_efficiency=0.9)
        assert r2["responsivity_a_per_w"] > r1["responsivity_a_per_w"]

    def test_responsivity_proportional_to_qe(self):
        """Higher QE → higher responsivity at same wavelength."""
        r1 = photodiode_responsivity(wavelength_m=850e-9, quantum_efficiency=0.5)
        r2 = photodiode_responsivity(wavelength_m=850e-9, quantum_efficiency=0.9)
        ratio = r2["responsivity_a_per_w"] / r1["responsivity_a_per_w"]
        assert abs(ratio - 0.9 / 0.5) < 1e-6

    def test_zero_wavelength_returns_error(self):
        res = photodiode_responsivity(wavelength_m=0.0)
        assert res["ok"] is False

    def test_qe_above_one_returns_error(self):
        res = photodiode_responsivity(wavelength_m=850e-9, quantum_efficiency=1.5)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 5. photodiode_photocurrent
# ═══════════════════════════════════════════════════════════════════════════════

class TestPhotodiodePhotocurrent:
    def test_i_ph_equals_r_times_p(self):
        """I_ph = R × P_opt exactly."""
        res = photodiode_photocurrent(optical_power_w=1e-3, responsivity_a_per_w=0.8)
        assert res["ok"] is True
        assert abs(res["photocurrent_a"] - 0.8e-3) < 1e-15

    def test_linear_in_power(self):
        """Doubling power → doubling current."""
        r1 = photodiode_photocurrent(1e-4, 0.5)
        r2 = photodiode_photocurrent(2e-4, 0.5)
        assert abs(r2["photocurrent_a"] / r1["photocurrent_a"] - 2.0) < 1e-9

    def test_zero_power_returns_error(self):
        res = photodiode_photocurrent(optical_power_w=0.0, responsivity_a_per_w=0.8)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 6. photodiode_noise
# ═══════════════════════════════════════════════════════════════════════════════

class TestPhotodiodeNoise:
    """Shot + dark + Johnson noise, SNR, NEP, D*."""

    def test_shot_noise_formula(self):
        """i_shot = sqrt(2·q·I_ph·B)."""
        p_opt = 1e-3
        r = 0.8
        b = 1e6
        i_ph = r * p_opt
        expected_shot = math.sqrt(2 * _Q * i_ph * b)
        res = photodiode_noise(
            optical_power_w=p_opt,
            responsivity_a_per_w=r,
            dark_current_a=0.0,
            bandwidth_hz=b,
            load_resistance_ohm=1e6,  # high Rload → thermal noise negligible
        )
        assert res["ok"] is True
        assert abs(res["i_shot_rms_a"] - expected_shot) < 1e-20

    def test_thermal_noise_formula(self):
        """i_thermal = sqrt(4·kB·T·B/R_L). Dominant when optical power is tiny."""
        b = 1e6
        rl = 50.0
        t = 290.0
        expected_thermal = math.sqrt(4 * _KB * t * b / rl)
        res = photodiode_noise(
            optical_power_w=1e-15,  # tiny optical power → shot noise negligible
            responsivity_a_per_w=0.1,
            dark_current_a=0.0,
            bandwidth_hz=b,
            load_resistance_ohm=rl,
            temp_k=t,
        )
        assert res["ok"] is True
        assert abs(res["i_thermal_rms_a"] - expected_thermal) / expected_thermal < 1e-6

    def test_snr_decreases_with_lower_power(self):
        """Lower optical power → lower SNR."""
        r1 = photodiode_noise(1e-3, 0.8, 1e-9, 1e6, 1e3)
        r2 = photodiode_noise(1e-6, 0.8, 1e-9, 1e6, 1e3)
        assert r1["snr_db"] > r2["snr_db"]

    def test_snr_too_low_warning(self):
        """SNR below minimum → warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = photodiode_noise(
                optical_power_w=1e-12,
                responsivity_a_per_w=0.1,
                dark_current_a=1e-6,
                bandwidth_hz=1e8,
                load_resistance_ohm=50.0,
                snr_min_db=30.0,
            )
            assert res["ok"] is True
            assert res["snr_ok"] is False
            assert len(w) > 0

    def test_nep_is_noise_over_r_sqrt_b(self):
        """NEP = i_noise / (R × sqrt(B))."""
        p_opt = 1e-6
        r = 0.5
        b = 1e6
        rl = 1e6
        res = photodiode_noise(p_opt, r, 0.0, b, rl)
        expected_nep = res["i_noise_rms_a"] / (r * math.sqrt(b))
        assert abs(res["nep_w_per_root_hz"] - expected_nep) / expected_nep < 1e-6

    def test_d_star_for_1mm2_detector(self):
        """D* = 0.1 / NEP (for 1 mm² = 1e-2 cm² detector)."""
        res = photodiode_noise(1e-6, 0.5, 0.0, 1e6, 1e6)
        expected_d_star = 0.1 / res["nep_w_per_root_hz"]
        assert abs(res["d_star_cm_root_hz_per_w"] - expected_d_star) / expected_d_star < 1e-6


# ═══════════════════════════════════════════════════════════════════════════════
# 7. photodiode_bandwidth
# ═══════════════════════════════════════════════════════════════════════════════

class TestPhotodiodeBandwidth:
    def test_rc_bandwidth_formula(self):
        """f_RC = 1/(2π·Cj·RL)."""
        cj = 1e-12  # 1 pF
        rl = 50.0
        res = photodiode_bandwidth(junction_capacitance_f=cj, load_resistance_ohm=rl)
        expected = 1.0 / (2.0 * math.pi * cj * rl)
        assert abs(res["f_rc_hz"] - expected) / expected < 1e-6
        assert res["f_3db_hz"] == res["f_rc_hz"]

    def test_transit_time_bandwidth(self):
        """f_transit = 0.45/τ_tr."""
        cj = 1e-12
        rl = 50.0
        tt = 1e-11  # 10 ps
        res = photodiode_bandwidth(cj, rl, transit_time_s=tt)
        f_tr = 0.45 / tt
        assert abs(res["f_transit_hz"] - f_tr) / f_tr < 1e-6

    def test_combined_bandwidth_less_than_both_limits(self):
        """f_3dB ≤ min(f_RC, f_transit)."""
        cj = 1e-12
        rl = 50.0
        tt = 50e-12  # 50 ps transit
        res = photodiode_bandwidth(cj, rl, transit_time_s=tt)
        assert res["f_3db_hz"] <= res["f_rc_hz"] + 1.0
        assert res["f_3db_hz"] <= res["f_transit_hz"] + 1.0

    def test_rc_limited_flag(self):
        """When f_RC < f_transit, rc_limited=True."""
        cj = 100e-12   # large Cj → low f_RC
        rl = 50.0
        tt = 1e-15     # tiny transit time → high f_transit
        res = photodiode_bandwidth(cj, rl, transit_time_s=tt)
        assert res["rc_limited"] is True
        assert res["transit_limited"] is False

    def test_zero_capacitance_returns_error(self):
        res = photodiode_bandwidth(junction_capacitance_f=0.0, load_resistance_ohm=50.0)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 8. tia_design
# ═══════════════════════════════════════════════════════════════════════════════

class TestTiaDesign:
    def test_transimpedance_gain_equals_rf(self):
        """Z_T = Rf."""
        res = tia_design(
            feedback_resistance_ohm=10e3,
            diode_capacitance_f=1e-12,
            opamp_voltage_noise_v_per_root_hz=4e-9,
            opamp_current_noise_a_per_root_hz=0.5e-12,
            bandwidth_hz=10e6,
        )
        assert res["ok"] is True
        assert res["transimpedance_gain_ohm"] == 10e3

    def test_johnson_noise_of_rf(self):
        """i_Rf = sqrt(4·kB·T·B/Rf)."""
        rf = 10e3
        b = 10e6
        t = 290.0
        res = tia_design(
            feedback_resistance_ohm=rf,
            diode_capacitance_f=1e-12,
            opamp_voltage_noise_v_per_root_hz=4e-9,
            opamp_current_noise_a_per_root_hz=0.5e-12,
            bandwidth_hz=b,
            temp_k=t,
        )
        expected_i_rf = math.sqrt(4 * _KB * t * b / rf)
        assert abs(res["i_rf_noise_rms_a"] - expected_i_rf) / expected_i_rf < 1e-6

    def test_total_noise_geq_rf_noise(self):
        """Total noise ≥ Johnson noise of Rf."""
        res = tia_design(
            feedback_resistance_ohm=10e3,
            diode_capacitance_f=1e-12,
            opamp_voltage_noise_v_per_root_hz=4e-9,
            opamp_current_noise_a_per_root_hz=0.5e-12,
            bandwidth_hz=10e6,
        )
        assert res["i_total_noise_rms_a"] >= res["i_rf_noise_rms_a"]

    def test_cf_positive_for_typical_inputs(self):
        """Cf > 0 for typical TIA parameters."""
        res = tia_design(
            feedback_resistance_ohm=10e3,
            diode_capacitance_f=5e-12,
            opamp_voltage_noise_v_per_root_hz=4e-9,
            opamp_current_noise_a_per_root_hz=0.5e-12,
            bandwidth_hz=1e6,
        )
        assert res["cf_stability_f"] > 0
        assert res["tia_stable"] is True

    def test_invalid_rf_returns_error(self):
        res = tia_design(
            feedback_resistance_ohm=0.0,
            diode_capacitance_f=1e-12,
            opamp_voltage_noise_v_per_root_hz=4e-9,
            opamp_current_noise_a_per_root_hz=0.5e-12,
            bandwidth_hz=10e6,
        )
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 9. optocoupler
# ═══════════════════════════════════════════════════════════════════════════════

class TestOptocoupler:
    def test_i_out_from_ctr(self):
        """I_out = (CTR/100) × I_F."""
        res = optocoupler(if_ma=10.0, ctr_percent=100.0, vcc_v=5.0, rload_ohm=1000.0)
        assert res["ok"] is True
        # I_out = 1.0 × 10e-3 = 10 mA
        assert abs(res["i_out_a"] - 10e-3) < 1e-12

    def test_v_out_capped_at_vcc(self):
        """V_out is capped at Vcc when I_out × R_load > Vcc."""
        res = optocoupler(if_ma=100.0, ctr_percent=200.0, vcc_v=5.0, rload_ohm=10e3)
        # I_out = 2.0 × 100e-3 = 200 mA; V_out_ideal = 200e-3 × 10e3 = 2000 V > 5 V
        assert res["saturated"] is True
        assert res["v_out_v"] == 5.0

    def test_bandwidth_scales_with_rload(self):
        """Bandwidth at Rload scales as 1/Rload from reference 1 kΩ."""
        bw_ref = 1e6  # at 1 kΩ
        rload = 10e3  # 10 kΩ → BW = 1e6 × 1e3/10e3 = 100 kHz
        res = optocoupler(if_ma=10.0, ctr_percent=100.0, vcc_v=5.0,
                          rload_ohm=rload, bandwidth_hz=bw_ref)
        expected_bw = bw_ref * 1e3 / rload
        assert abs(res["bandwidth_hz_at_rload"] - expected_bw) < 1.0

    def test_zero_if_returns_error(self):
        res = optocoupler(if_ma=0.0, ctr_percent=100.0, vcc_v=5.0, rload_ohm=1e3)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 10. fiber_coupling_efficiency
# ═══════════════════════════════════════════════════════════════════════════════

class TestFiberCoupling:
    def test_perfect_match_unity_efficiency(self):
        """Equal NA and equal mode diameter → η_mode = 1, η = 1."""
        res = fiber_coupling_efficiency(
            source_na=0.12, fiber_na=0.12,
            source_mode_diameter_m=10e-6, fiber_mode_diameter_m=10e-6
        )
        assert res["ok"] is True
        assert abs(res["coupling_efficiency"] - 1.0) < 1e-6
        assert res["coupling_loss_db"] < 0.001

    def test_na_mismatch_reduces_efficiency(self):
        """Source NA > fiber NA → η_NA < 1 → η < 1."""
        res = fiber_coupling_efficiency(
            source_na=0.3, fiber_na=0.12,
            source_mode_diameter_m=10e-6, fiber_mode_diameter_m=10e-6
        )
        assert res["na_efficiency"] < 1.0
        assert res["coupling_efficiency"] < 1.0

    def test_mode_mismatch_reduces_efficiency(self):
        """Different mode diameters → mode overlap < 1."""
        res = fiber_coupling_efficiency(
            source_na=0.12, fiber_na=0.12,
            source_mode_diameter_m=5e-6, fiber_mode_diameter_m=10e-6
        )
        assert res["mode_overlap_efficiency"] < 1.0

    def test_coupling_loss_db_consistent_with_efficiency(self):
        """coupling_loss_db = -10·log10(coupling_efficiency)."""
        res = fiber_coupling_efficiency(
            source_na=0.2, fiber_na=0.12,
            source_mode_diameter_m=8e-6, fiber_mode_diameter_m=10e-6
        )
        expected_loss = -10 * math.log10(res["coupling_efficiency"])
        assert abs(res["coupling_loss_db"] - expected_loss) < 0.001

    def test_zero_na_returns_error(self):
        res = fiber_coupling_efficiency(
            source_na=0.0, fiber_na=0.12,
            source_mode_diameter_m=10e-6, fiber_mode_diameter_m=10e-6
        )
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 11. solar_cell_iv
# ═══════════════════════════════════════════════════════════════════════════════

class TestSolarCellIV:
    """Single-diode model, FF, efficiency."""

    def test_ok_returns_required_keys(self):
        res = solar_cell_iv(isc_a=8.0, voc_v=0.6)
        assert res["ok"] is True
        for k in ("ff", "pmpp_w", "vmpp_v", "impp_a", "efficiency", "vt_v", "i0_a"):
            assert k in res, f"Missing key {k!r}"

    def test_ff_in_valid_range(self):
        """0 < FF < 1."""
        res = solar_cell_iv(isc_a=8.0, voc_v=0.6, temp_k=300.0)
        assert 0.0 < res["ff"] < 1.0

    def test_pmpp_leq_isc_voc(self):
        """Pmpp = FF × Voc × Isc ≤ Voc × Isc."""
        res = solar_cell_iv(isc_a=8.0, voc_v=0.6)
        assert res["pmpp_w"] <= 8.0 * 0.6 + 1e-9

    def test_efficiency_reasonable(self):
        """Efficiency for typical Si cell at 1-sun: 10–25% for ~240 cm² cell.
        Isc=8A, Voc=0.6V → Pmpp ≈ FF×4.8 W; area=240cm²=0.024m² →
        P_in=1000×0.024=24W → η≈0.4×4.8/24≈20%."""
        res = solar_cell_iv(
            isc_a=8.0, voc_v=0.6,
            irradiance_w_per_m2=1000.0, cell_area_m2=240e-4
        )
        assert 0.05 < res["efficiency"] < 0.30

    def test_higher_voc_higher_ff(self):
        """Higher Voc/Vt ratio → higher ideal FF."""
        r_low = solar_cell_iv(isc_a=8.0, voc_v=0.4, temp_k=300.0)
        r_high = solar_cell_iv(isc_a=8.0, voc_v=0.7, temp_k=300.0)
        assert r_high["ff_ideal"] > r_low["ff_ideal"]

    def test_series_resistance_degrades_ff(self):
        """Non-zero series resistance → lower FF than ideal."""
        r_ideal = solar_cell_iv(isc_a=8.0, voc_v=0.6, series_resistance_ohm=0.0)
        r_rs = solar_cell_iv(isc_a=8.0, voc_v=0.6, series_resistance_ohm=0.5)
        assert r_rs["ff"] <= r_ideal["ff"] + 1e-6

    def test_vt_formula(self):
        """Vt = kB·T/q."""
        t = 300.0
        res = solar_cell_iv(isc_a=8.0, voc_v=0.6, temp_k=t)
        expected_vt = _KB * t / _Q
        assert abs(res["vt_v"] - expected_vt) < 1e-8

    def test_zero_isc_returns_error(self):
        res = solar_cell_iv(isc_a=0.0, voc_v=0.6)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 12. tof_lidar
# ═══════════════════════════════════════════════════════════════════════════════

class TestTofLidar:
    def test_tof_formula(self):
        """ToF round-trip = 2·R/c."""
        R = 100.0
        res = tof_lidar(
            peak_power_w=1.0, target_reflectivity=0.1, target_distance_m=R,
            aperture_diameter_m=0.05, receiver_responsivity_a_per_w=0.8,
            dark_current_a=1e-9, bandwidth_hz=1e7, load_resistance_ohm=1e3
        )
        assert res["ok"] is True
        expected_tof = 2 * R / _C
        assert abs(res["tof_s"] - expected_tof) / expected_tof < 1e-9

    def test_closer_target_higher_p_rx(self):
        """Closer target → higher received power."""
        common = dict(
            peak_power_w=1.0, target_reflectivity=0.1,
            aperture_diameter_m=0.05, receiver_responsivity_a_per_w=0.8,
            dark_current_a=1e-9, bandwidth_hz=1e7, load_resistance_ohm=1e3
        )
        r_close = tof_lidar(target_distance_m=10.0, **common)
        r_far = tof_lidar(target_distance_m=100.0, **common)
        assert r_close["p_rx_w"] > r_far["p_rx_w"]

    def test_snr_too_low_warning(self):
        """Very far target → low SNR → warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = tof_lidar(
                peak_power_w=1e-4, target_reflectivity=0.01,
                target_distance_m=10000.0,
                aperture_diameter_m=0.01, receiver_responsivity_a_per_w=0.5,
                dark_current_a=1e-8, bandwidth_hz=1e8, load_resistance_ohm=50.0,
                snr_min_db=20.0
            )
            assert res["ok"] is True
            assert res["snr_ok"] is False
            assert len(w) > 0

    def test_range_limit_at_current_snr_min_equals_distance(self):
        """When SNR == snr_min, range_limit ≈ target_distance."""
        res = tof_lidar(
            peak_power_w=1.0, target_reflectivity=0.1, target_distance_m=50.0,
            aperture_diameter_m=0.05, receiver_responsivity_a_per_w=0.8,
            dark_current_a=1e-9, bandwidth_hz=1e7, load_resistance_ohm=1e3,
            snr_min_db=res_at_50_db if (res_at_50_db := tof_lidar(
                peak_power_w=1.0, target_reflectivity=0.1, target_distance_m=50.0,
                aperture_diameter_m=0.05, receiver_responsivity_a_per_w=0.8,
                dark_current_a=1e-9, bandwidth_hz=1e7, load_resistance_ohm=1e3
            )["snr_db"]) else 0.0
        )
        # Range limit should be close to 50 m
        assert abs(res["range_limit_m"] - 50.0) < 5.0

    def test_invalid_reflectivity_returns_error(self):
        res = tof_lidar(
            peak_power_w=1.0, target_reflectivity=1.5,
            target_distance_m=50.0, aperture_diameter_m=0.05,
            receiver_responsivity_a_per_w=0.8, dark_current_a=1e-9,
            bandwidth_hz=1e7, load_resistance_ohm=1e3
        )
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 13. LLM tool handlers (async, stub registry)
# ═══════════════════════════════════════════════════════════════════════════════

class TestToolHandlers:
    @pytest.mark.asyncio
    async def test_wavelength_to_energy_tool_ok(self):
        res = await call(tool_wavelength_to_energy, wavelength_m=1550e-9)
        assert res["ok"] is True
        assert "photon_energy_ev" in res

    @pytest.mark.asyncio
    async def test_led_liv_tool_ok(self):
        res = await call(
            tool_led_liv,
            current_a=0.05, wavelength_m=850e-9, slope_efficiency_w_per_a=0.5,
            threshold_current_a=0.01, vf_v=2.0
        )
        assert res["ok"] is True
        assert "p_opt_w" in res

    @pytest.mark.asyncio
    async def test_laser_threshold_tool_ok(self):
        res = await call(
            tool_laser_threshold,
            current_a=0.05, threshold_current_a=0.02, slope_efficiency_w_per_a=0.3
        )
        assert res["ok"] is True
        assert "above_threshold" in res

    @pytest.mark.asyncio
    async def test_pd_responsivity_tool_ok(self):
        res = await call(tool_pd_responsivity, wavelength_m=1550e-9, quantum_efficiency=0.9)
        assert res["ok"] is True
        assert "responsivity_a_per_w" in res

    @pytest.mark.asyncio
    async def test_pd_photocurrent_tool_ok(self):
        res = await call(tool_pd_photocurrent, optical_power_w=1e-3, responsivity_a_per_w=0.8)
        assert res["ok"] is True
        assert "photocurrent_a" in res

    @pytest.mark.asyncio
    async def test_pd_noise_tool_ok(self):
        res = await call(
            tool_pd_noise,
            optical_power_w=1e-3, responsivity_a_per_w=0.8, dark_current_a=1e-9,
            bandwidth_hz=1e6, load_resistance_ohm=1e3
        )
        assert res["ok"] is True
        assert "snr_db" in res
        assert "nep_w_per_root_hz" in res

    @pytest.mark.asyncio
    async def test_pd_bandwidth_tool_ok(self):
        res = await call(
            tool_pd_bandwidth,
            junction_capacitance_f=1e-12, load_resistance_ohm=50.0
        )
        assert res["ok"] is True
        assert "f_3db_hz" in res

    @pytest.mark.asyncio
    async def test_tia_design_tool_ok(self):
        res = await call(
            tool_tia_design,
            feedback_resistance_ohm=10e3, diode_capacitance_f=1e-12,
            opamp_voltage_noise_v_per_root_hz=4e-9,
            opamp_current_noise_a_per_root_hz=0.5e-12,
            bandwidth_hz=10e6
        )
        assert res["ok"] is True
        assert "cf_stability_f" in res

    @pytest.mark.asyncio
    async def test_optocoupler_tool_ok(self):
        res = await call(
            tool_optocoupler,
            if_ma=10.0, ctr_percent=100.0, vcc_v=5.0, rload_ohm=1e3
        )
        assert res["ok"] is True
        assert "i_out_a" in res

    @pytest.mark.asyncio
    async def test_fiber_coupling_tool_ok(self):
        res = await call(
            tool_fiber_coupling,
            source_na=0.12, fiber_na=0.12,
            source_mode_diameter_m=10e-6, fiber_mode_diameter_m=10e-6
        )
        assert res["ok"] is True
        assert "coupling_efficiency" in res

    @pytest.mark.asyncio
    async def test_solar_cell_tool_ok(self):
        res = await call(tool_solar_cell_iv, isc_a=8.0, voc_v=0.6)
        assert res["ok"] is True
        assert "ff" in res
        assert "efficiency" in res

    @pytest.mark.asyncio
    async def test_tof_lidar_tool_ok(self):
        res = await call(
            tool_tof_lidar,
            peak_power_w=1.0, target_reflectivity=0.1, target_distance_m=50.0,
            aperture_diameter_m=0.05, receiver_responsivity_a_per_w=0.8,
            dark_current_a=1e-9, bandwidth_hz=1e7, load_resistance_ohm=1e3
        )
        assert res["ok"] is True
        assert "range_limit_m" in res

    @pytest.mark.asyncio
    async def test_tool_invalid_json_returns_error(self):
        result = await tool_pd_noise(None, b"not valid json{{")
        data = json.loads(result)
        assert data.get("ok") is False or "error" in data

    @pytest.mark.asyncio
    async def test_tool_zero_wavelength_returns_error(self):
        result = await tool_wavelength_to_energy(
            None, json.dumps({"wavelength_m": 0.0}).encode()
        )
        data = json.loads(result)
        assert data.get("ok") is False or "error" in data
