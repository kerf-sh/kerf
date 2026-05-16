"""
Hermetic tests for the RF & fiber-optic link budget module.

Tests are cross-checked against hand-calculations from standard comms texts:
  - Rappaport, "Wireless Communications" (Prentice Hall, 2002)
  - Pozar, "Microwave Engineering" (Wiley, 2012)
  - Saleh & Teich, "Fundamentals of Photonics" (Wiley, 2019)
  - Proakis & Salehi, "Digital Communications" (McGraw-Hill, 2008)
  - Shannon, "A Mathematical Theory of Communication" (1948)
  - ITU-R P.838-3, ITU-R P.676-12

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

from kerf_electronics.linkbudget.link import (
    fspl_db,
    eirp_dbw,
    received_power_dbw,
    antenna_gain_from_aperture,
    antenna_aperture_from_gain,
    g_over_t,
    noise_figure_cascade,
    system_noise_temp,
    thermal_noise_floor_dbw,
    cn_ratio_db,
    eb_n0_db,
    required_eb_n0_bpsk,
    required_eb_n0_qpsk,
    required_eb_n0_qam,
    required_eb_n0_psk,
    ber_bpsk,
    ber_qpsk,
    ber_qam,
    ber_psk,
    shannon_capacity,
    spectral_efficiency,
    rain_attenuation_db,
    atmospheric_attenuation_db,
    rf_link_budget,
    fiber_power_budget,
    chromatic_dispersion_bandwidth,
    modal_dispersion_bandwidth,
    fiber_osnr,
    _erfc,
    _q_func,
)

# ── Load tool module via importlib so stub is active ─────────────────────────
_tool_spec = importlib.util.spec_from_file_location(
    "kerf_electronics.linkbudget.tools",
    os.path.join(_SRC, "kerf_electronics", "linkbudget", "tools.py"),
)
_tool_mod = importlib.util.module_from_spec(_tool_spec)
_tool_spec.loader.exec_module(_tool_mod)


# ── Async call helper ─────────────────────────────────────────────────────────
async def call(fn, **kwargs):
    result = await fn(None, json.dumps(kwargs).encode())
    return json.loads(result)


# =============================================================================
# 1. Free-space path loss
# =============================================================================

class TestFSPL:
    """Hand-calc: at 1 GHz, 1 km: FSPL = 20*log10(4π*1000*1e9/c) ≈ 92.45 dB"""

    def test_fspl_1ghz_1km(self):
        """Classic reference: 1 GHz, 1 km → ~92.45 dB."""
        res = fspl_db(freq_hz=1e9, distance_m=1000.0)
        assert res["ok"] is True
        # 20*log10(4*pi*1000*1e9 / 2.998e8) = 20*log10(4*pi*1e12/2.998e8)
        expected = 20.0 * math.log10(4.0 * math.pi * 1000.0 * 1e9 / 2.99792458e8)
        assert abs(res["fspl_db"] - expected) < 0.01, f"Expected {expected:.2f}, got {res['fspl_db']}"

    def test_fspl_scales_with_distance(self):
        """Doubling distance → +6 dB FSPL."""
        r1 = fspl_db(freq_hz=2.4e9, distance_m=100.0)
        r2 = fspl_db(freq_hz=2.4e9, distance_m=200.0)
        diff = r2["fspl_db"] - r1["fspl_db"]
        assert abs(diff - 6.020) < 0.01, f"Expected ~6 dB, got {diff:.3f}"

    def test_fspl_scales_with_frequency(self):
        """Doubling frequency → +6 dB FSPL."""
        r1 = fspl_db(freq_hz=1e9, distance_m=500.0)
        r2 = fspl_db(freq_hz=2e9, distance_m=500.0)
        diff = r2["fspl_db"] - r1["fspl_db"]
        assert abs(diff - 6.020) < 0.01, f"Expected ~6 dB, got {diff:.3f}"

    def test_fspl_zero_freq_returns_error(self):
        res = fspl_db(freq_hz=0, distance_m=1000.0)
        assert res["ok"] is False

    def test_fspl_negative_distance_returns_error(self):
        res = fspl_db(freq_hz=1e9, distance_m=-1.0)
        assert res["ok"] is False

    def test_fspl_wavelength_correct(self):
        """Wavelength = c/f = 0.3 m at 1 GHz."""
        res = fspl_db(freq_hz=1e9, distance_m=1000.0)
        assert abs(res["wavelength_m"] - 0.29979) < 0.001


# =============================================================================
# 2. EIRP
# =============================================================================

class TestEIRP:
    def test_eirp_basic(self):
        """0 dBW + 10 dBi → 10 dBW EIRP."""
        res = eirp_dbw(p_tx_dbw=0.0, g_tx_dbi=10.0)
        assert res["ok"] is True
        assert abs(res["eirp_dbw"] - 10.0) < 1e-9

    def test_eirp_dbm_offset(self):
        """EIRP dBm = dBW + 30."""
        res = eirp_dbw(p_tx_dbw=5.0, g_tx_dbi=3.0)
        assert abs(res["eirp_dbm"] - (res["eirp_dbw"] + 30.0)) < 1e-9

    def test_eirp_negative_gain(self):
        """Negative gain (attenuator) still returns ok."""
        res = eirp_dbw(p_tx_dbw=10.0, g_tx_dbi=-3.0)
        assert res["ok"] is True
        assert abs(res["eirp_dbw"] - 7.0) < 1e-9


# =============================================================================
# 3. Thermal noise floor
# =============================================================================

class TestThermalNoise:
    """kTB: at T=290K, B=1Hz → N = -174 dBm/Hz (classic result)."""

    def test_ktb_1hz_290k(self):
        """N = k × 290 × 1 Hz → -174.0 dBm/Hz."""
        res = thermal_noise_floor_dbw(bandwidth_hz=1.0, temp_k=290.0)
        assert res["ok"] is True
        # k*290*1 in W, convert to dBm
        noise_dbm = res["noise_dbm"]
        assert abs(noise_dbm - (-174.0)) < 0.1, f"Expected ~-174 dBm, got {noise_dbm:.2f}"

    def test_ktb_1mhz_bandwidth(self):
        """1 MHz BW at 290K → -114 dBm."""
        res = thermal_noise_floor_dbw(bandwidth_hz=1e6, temp_k=290.0)
        assert res["ok"] is True
        assert abs(res["noise_dbm"] - (-114.0)) < 0.2

    def test_ktb_zero_bandwidth_returns_error(self):
        res = thermal_noise_floor_dbw(bandwidth_hz=0, temp_k=290.0)
        assert res["ok"] is False

    def test_ktb_zero_temp_returns_error(self):
        res = thermal_noise_floor_dbw(bandwidth_hz=1e6, temp_k=0)
        assert res["ok"] is False


# =============================================================================
# 4. Noise figure cascade
# =============================================================================

class TestNoiseCascade:
    """Friis formula: F_total = F1 + (F2-1)/G1 + ..."""

    def test_single_stage(self):
        """Single stage: cascade NF = stage NF."""
        res = noise_figure_cascade(nf_db_list=[3.0], gain_db_list=[20.0])
        assert res["ok"] is True
        assert abs(res["nf_cascade_db"] - 3.0) < 0.01

    def test_high_gain_first_stage_dominates(self):
        """If G1 >> 1, F_total ≈ F1 (second stage negligible)."""
        # LNA: NF=1.5 dB, Gain=30 dB; then mixer: NF=8 dB
        res = noise_figure_cascade(
            nf_db_list=[1.5, 8.0],
            gain_db_list=[30.0, 10.0],
        )
        assert res["ok"] is True
        # Total NF should be close to 1.5 dB
        assert res["nf_cascade_db"] < 1.6, f"Got {res['nf_cascade_db']:.3f}"

    def test_friis_two_stage_hand_calc(self):
        """NF1=3dB(F1=2), G1=10dB(G=10); NF2=10dB(F2=10).
        F_total = 2 + (10-1)/10 = 2.9 → NF = 10*log10(2.9) ≈ 4.62 dB"""
        res = noise_figure_cascade(nf_db_list=[3.0, 10.0], gain_db_list=[10.0, 10.0])
        assert res["ok"] is True
        expected = 10.0 * math.log10(2.0 + 9.0 / 10.0)
        assert abs(res["nf_cascade_db"] - expected) < 0.01

    def test_mismatched_lists_returns_error(self):
        res = noise_figure_cascade(nf_db_list=[3.0, 5.0], gain_db_list=[10.0])
        assert res["ok"] is False

    def test_empty_list_returns_error(self):
        res = noise_figure_cascade(nf_db_list=[], gain_db_list=[])
        assert res["ok"] is False


# =============================================================================
# 5. System noise temperature
# =============================================================================

class TestSystemNoiseTemp:
    def test_0db_nf_gives_0_noise_temp(self):
        """NF=0 dB → F=1 → T_noise = T0*(1-1) = 0 K."""
        res = system_noise_temp(nf_total_db=0.0, t_ant_k=0.0)
        assert res["ok"] is True
        assert abs(res["t_noise_k"]) < 0.01

    def test_3db_nf(self):
        """NF=3 dB → F≈2 → T_noise ≈ 290 K."""
        res = system_noise_temp(nf_total_db=3.0103, t_ant_k=0.0)
        assert res["ok"] is True
        assert abs(res["t_noise_k"] - 290.0) < 1.0

    def test_antenna_temp_added(self):
        """T_sys = T_ant + T_noise."""
        res = system_noise_temp(nf_total_db=3.0103, t_ant_k=50.0)
        assert res["ok"] is True
        assert abs(res["t_sys_k"] - res["t_noise_k"] - 50.0) < 0.1


# =============================================================================
# 6. BPSK BER
# =============================================================================

class TestBPSKBER:
    """Hand-calcs from Proakis & Salehi, "Digital Communications" §8.2."""

    def test_bpsk_ber_at_eb_n0_9_6db(self):
        """Eb/N0 = 9.6 dB ≈ 9.12 linear → BER ≈ 1e-5 for BPSK.
        BER = 0.5*erfc(sqrt(9.12)) ≈ 0.5*erfc(3.02) ≈ 1e-5."""
        eb_n0_linear = 10.0 ** (9.6 / 10.0)
        ber_val = ber_bpsk(eb_n0_linear)
        assert ber_val < 1e-4, f"BER should be ~1e-5, got {ber_val:.2e}"
        assert ber_val > 1e-7

    def test_bpsk_ber_eb_n0_0db_is_half(self):
        """Eb/N0 = 0 dB (linear=1) → BER = 0.5*erfc(1) ≈ 0.157."""
        ber_val = ber_bpsk(1.0)
        expected = 0.5 * _erfc(1.0)
        assert abs(ber_val - expected) < 1e-7

    def test_bpsk_ber_decreases_with_snr(self):
        ber_low = ber_bpsk(10.0 ** (0.0 / 10.0))
        ber_high = ber_bpsk(10.0 ** (10.0 / 10.0))
        assert ber_high < ber_low

    def test_qpsk_same_as_bpsk_per_bit(self):
        """QPSK BER per bit equals BPSK BER at the same Eb/N0."""
        ebn0_linear = 10.0 ** (8.0 / 10.0)
        assert abs(ber_bpsk(ebn0_linear) - ber_qpsk(ebn0_linear)) < 1e-12

    def test_required_ebn0_bpsk_1e6(self):
        """Required Eb/N0 for BER=1e-6 with BPSK: ~10.5 dB."""
        res = required_eb_n0_bpsk(1e-6)
        assert res["ok"] is True
        assert 9.5 < res["eb_n0_db"] < 11.5, f"Got {res['eb_n0_db']:.2f} dB"

    def test_required_ebn0_round_trip(self):
        """Compute required Eb/N0, then verify BER at that point ≈ target."""
        target = 1e-5
        res = required_eb_n0_bpsk(target)
        assert res["ok"] is True
        ber_check = ber_bpsk(res["eb_n0_linear"])
        # Allow 20% relative error due to erfc approximation
        assert abs(ber_check - target) / target < 0.2, (
            f"Round-trip BER {ber_check:.2e} vs target {target:.2e}"
        )


# =============================================================================
# 7. QAM BER
# =============================================================================

class TestQAMBER:
    def test_4qam_ber_plausible(self):
        """4-QAM BER is between BPSK and 64-QAM at 0 dB Eb/N0.
        At 0 dB linear (1.0): 4-QAM BER ≈ 0.023, BPSK ≈ 0.079, 64-QAM higher."""
        ebn0_linear = 1.0  # 0 dB
        ber_4qam = ber_qam(ebn0_linear, 4)
        ber_bpsk_val = ber_bpsk(ebn0_linear)
        ber_64qam = ber_qam(ebn0_linear, 64)
        # 4-QAM should be within a factor of 10 of BPSK
        assert ber_4qam > 0
        assert ber_4qam < ber_64qam
        # At 0 dB, 4-QAM BER is in (0.01, 0.15)
        assert 0.005 < ber_4qam < 0.15

    def test_64qam_needs_more_ebn0_than_bpsk(self):
        """At same Eb/N0, 64-QAM has worse BER than BPSK."""
        ebn0_linear = 10.0 ** (10.0 / 10.0)
        assert ber_qam(ebn0_linear, 64) > ber_bpsk(ebn0_linear)

    def test_required_ebn0_64qam_1e6(self):
        """64-QAM needs more Eb/N0 than BPSK for same BER."""
        res_bpsk = required_eb_n0_bpsk(1e-6)
        res_qam = required_eb_n0_qam(1e-6, 64)
        assert res_qam["ok"] is True
        assert res_qam["eb_n0_db"] > res_bpsk["eb_n0_db"]

    def test_ber_qam_invalid_m_raises(self):
        """Non-power-of-2 m should raise ValueError (internal function)."""
        with pytest.raises(ValueError):
            ber_qam(10.0, 3)

    def test_required_ebn0_qam_invalid_m_returns_error(self):
        res = required_eb_n0_qam(1e-6, 3)
        assert res["ok"] is False


# =============================================================================
# 8. Shannon capacity
# =============================================================================

class TestShannonCapacity:
    """C = B × log2(1 + SNR)"""

    def test_shannon_1hz_0db(self):
        """B=1 Hz, SNR=0 dB (linear=1) → C = log2(2) = 1 bps."""
        res = shannon_capacity(bandwidth_hz=1.0, snr_db=0.0)
        assert res["ok"] is True
        assert abs(res["capacity_bps"] - 1.0) < 1e-9
        assert abs(res["spectral_efficiency_bps_per_hz"] - 1.0) < 1e-9

    def test_shannon_scales_with_bandwidth(self):
        """Doubling bandwidth → doubling capacity (at fixed SNR)."""
        r1 = shannon_capacity(bandwidth_hz=1e6, snr_db=10.0)
        r2 = shannon_capacity(bandwidth_hz=2e6, snr_db=10.0)
        assert abs(r2["capacity_bps"] / r1["capacity_bps"] - 2.0) < 1e-9

    def test_shannon_high_snr(self):
        """At SNR=30 dB (1000 linear): η ≈ log2(1001) ≈ 9.97 bps/Hz."""
        res = shannon_capacity(bandwidth_hz=1.0, snr_db=30.0)
        assert res["ok"] is True
        expected_eta = math.log2(1.0 + 1000.0)
        assert abs(res["spectral_efficiency_bps_per_hz"] - expected_eta) < 0.001

    def test_shannon_negative_snr(self):
        """Negative SNR still returns ok (channel can still carry some info)."""
        res = shannon_capacity(bandwidth_hz=1e6, snr_db=-10.0)
        assert res["ok"] is True
        assert res["capacity_bps"] > 0

    def test_spectral_efficiency_standalone(self):
        """spectral_efficiency function agrees with shannon_capacity."""
        res_shan = shannon_capacity(bandwidth_hz=1.0, snr_db=20.0)
        res_se = spectral_efficiency(snr_db=20.0)
        assert res_se["ok"] is True
        assert abs(res_shan["spectral_efficiency_bps_per_hz"] - res_se["spectral_efficiency_bps_per_hz"]) < 1e-9

    def test_shannon_6bits_per_hz_at_63snr(self):
        """SNR = 63 (linear) → η = log2(64) = 6 bps/Hz."""
        res = shannon_capacity(bandwidth_hz=1.0, snr_db=10.0 * math.log10(63.0))
        assert abs(res["spectral_efficiency_bps_per_hz"] - 6.0) < 0.01


# =============================================================================
# 9. Antenna gain ↔ aperture
# =============================================================================

class TestAntennaGainAperture:
    def test_gain_aperture_round_trip(self):
        """gain_from_aperture → aperture_from_gain round-trip."""
        g_dbi = 25.0
        freq = 10e9
        res_ap = antenna_aperture_from_gain(gain_dbi=g_dbi, freq_hz=freq)
        assert res_ap["ok"] is True
        res_g = antenna_gain_from_aperture(aperture_m2=res_ap["aperture_m2"], freq_hz=freq)
        assert res_g["ok"] is True
        assert abs(res_g["gain_dbi"] - g_dbi) < 0.01

    def test_gain_scales_with_frequency_squared(self):
        """Doubling frequency → +6 dB gain for fixed aperture."""
        r1 = antenna_gain_from_aperture(aperture_m2=0.1, freq_hz=10e9)
        r2 = antenna_gain_from_aperture(aperture_m2=0.1, freq_hz=20e9)
        assert abs(r2["gain_dbi"] - r1["gain_dbi"] - 6.02) < 0.01


# =============================================================================
# 10. G/T
# =============================================================================

class TestGOverT:
    def test_g_over_t_basic(self):
        """G=30 dBi, T=290 K → G/T = 30 - 10*log10(290) ≈ 5.37 dB/K."""
        res = g_over_t(g_rx_dbi=30.0, t_sys_k=290.0)
        assert res["ok"] is True
        expected = 30.0 - 10.0 * math.log10(290.0)
        assert abs(res["g_over_t_db_per_k"] - expected) < 0.01

    def test_g_over_t_zero_temp_returns_error(self):
        res = g_over_t(g_rx_dbi=30.0, t_sys_k=0.0)
        assert res["ok"] is False


# =============================================================================
# 11. Rain attenuation
# =============================================================================

class TestRainAttenuation:
    def test_rain_10ghz_moderate(self):
        """At 10 GHz, 25 mm/h rain rate, 1 km: ~0.25 dB (k=0.0101, α=1.276)."""
        res = rain_attenuation_db(
            freq_hz=10e9,
            rain_rate_mm_per_hr=25.0,
            path_length_km=1.0,
        )
        assert res["ok"] is True
        # γ_R = k * R^α = 0.0101 * 25^1.276
        k, alpha = 0.0101, 1.276
        expected = k * (25.0 ** alpha) * 1.0
        assert abs(res["a_rain_db"] - expected) < 0.05

    def test_rain_scales_linearly_with_path(self):
        """Total attenuation scales linearly with path length."""
        r1 = rain_attenuation_db(freq_hz=20e9, rain_rate_mm_per_hr=50.0, path_length_km=1.0)
        r2 = rain_attenuation_db(freq_hz=20e9, rain_rate_mm_per_hr=50.0, path_length_km=5.0)
        assert r2["ok"] and r1["ok"]
        assert abs(r2["a_rain_db"] / r1["a_rain_db"] - 5.0) < 0.01

    def test_rain_returns_error_for_zero_rate(self):
        res = rain_attenuation_db(freq_hz=10e9, rain_rate_mm_per_hr=0.0, path_length_km=1.0)
        assert res["ok"] is False


# =============================================================================
# 12. Full RF link budget
# =============================================================================

class TestRFLinkBudget:
    def test_basic_link_passes(self):
        """Simple LEO-like link that should pass."""
        res = rf_link_budget(
            p_tx_dbw=10.0,        # 10 W transmitter
            g_tx_dbi=10.0,
            g_rx_dbi=30.0,
            freq_hz=2.4e9,
            distance_m=100e3,     # 100 km
            noise_figure_db=3.0,
            bandwidth_hz=1e6,
            required_snr_db=10.0,
        )
        assert res["ok"] is True
        assert res["passes"] is True
        assert res["margin_db"] >= 0.0

    def test_link_fails_at_extreme_distance(self):
        """Same link but at 10,000 km should fail."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = rf_link_budget(
                p_tx_dbw=0.0,
                g_tx_dbi=0.0,
                g_rx_dbi=0.0,
                freq_hz=1e9,
                distance_m=1e7,   # 10,000 km
                noise_figure_db=3.0,
                bandwidth_hz=1e6,
                required_snr_db=10.0,
            )
        assert res["ok"] is True
        assert res["passes"] is False
        assert res["margin_db"] < 0.0
        assert len(w) >= 1  # warning should be issued

    def test_margin_equals_cn_minus_required_snr(self):
        """margin_db = cn_db - required_snr_db."""
        res = rf_link_budget(
            p_tx_dbw=5.0,
            g_tx_dbi=5.0,
            g_rx_dbi=15.0,
            freq_hz=5.8e9,
            distance_m=1000.0,
            noise_figure_db=5.0,
            bandwidth_hz=20e6,
            required_snr_db=20.0,
        )
        assert res["ok"] is True
        assert abs(res["margin_db"] - (res["cn_db"] - 20.0)) < 0.01


# =============================================================================
# 13. Fiber power budget
# =============================================================================

class TestFiberPowerBudget:
    def test_basic_fiber_passes(self):
        """Short SMF link with plenty of margin."""
        res = fiber_power_budget(
            p_tx_dbm=0.0,           # 1 mW
            rx_sensitivity_dbm=-30.0,
            fiber_loss_db_per_km=0.35,
            length_km=10.0,
            connector_loss_db=1.0,
            splice_loss_db=0.5,
            safety_margin_db=3.0,
        )
        assert res["ok"] is True
        assert res["passes"] is True

    def test_long_link_fails(self):
        """100 km × 0.35 dB/km = 35 dB fiber loss — too long for this budget."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = fiber_power_budget(
                p_tx_dbm=0.0,
                rx_sensitivity_dbm=-25.0,
                fiber_loss_db_per_km=0.35,
                length_km=100.0,
                connector_loss_db=2.0,
                splice_loss_db=1.0,
                safety_margin_db=3.0,
            )
        assert res["ok"] is True
        assert res["passes"] is False
        assert len(w) >= 1

    def test_margin_formula(self):
        """margin = (P_tx - Rx_sens) - (fiber_loss + connectors + splices + safety)."""
        p_tx = 3.0
        rx_sens = -20.0
        loss_km = 0.2
        km = 50.0
        conn = 1.0
        splice = 0.5
        safety = 3.0
        res = fiber_power_budget(
            p_tx_dbm=p_tx,
            rx_sensitivity_dbm=rx_sens,
            fiber_loss_db_per_km=loss_km,
            length_km=km,
            connector_loss_db=conn,
            splice_loss_db=splice,
            safety_margin_db=safety,
        )
        assert res["ok"] is True
        available = p_tx - rx_sens
        penalty = loss_km * km + conn + splice + safety
        expected_margin = available - penalty
        assert abs(res["margin_db"] - expected_margin) < 0.001

    def test_fiber_budget_zero_length_returns_error(self):
        res = fiber_power_budget(
            p_tx_dbm=0.0,
            rx_sensitivity_dbm=-20.0,
            fiber_loss_db_per_km=0.2,
            length_km=0.0,
        )
        assert res["ok"] is False


# =============================================================================
# 14. Chromatic dispersion bandwidth
# =============================================================================

class TestChromaticDispersion:
    def test_smf28_1550nm_hand_calc(self):
        """SMF-28 at 1550 nm: D=17 ps/nm/km, L=100 km, Δλ=0.1 nm.
        CD_total = 17 × 100 × 0.1 = 170 ps → BW_limit = 1/(4×170e-12) ≈ 1.47 Gbps."""
        res = chromatic_dispersion_bandwidth(
            dispersion_ps_per_nm_km=17.0,
            length_km=100.0,
            source_linewidth_nm=0.1,
        )
        assert res["ok"] is True
        assert abs(res["cd_total_ps"] - 170.0) < 0.01
        expected_bw = 1.0 / (4.0 * 170.0e-12)
        assert abs(res["bw_limit_bps"] / expected_bw - 1.0) < 0.01

    def test_dispersion_limited_flag_set(self):
        """BW_limit < requested bit_rate → dispersion_limited=True."""
        res = chromatic_dispersion_bandwidth(
            dispersion_ps_per_nm_km=17.0,
            length_km=100.0,
            source_linewidth_nm=0.5,
            bit_rate_bps=10e9,
        )
        assert res["ok"] is True
        assert res["dispersion_limited"] is True

    def test_dispersion_not_limited(self):
        """Very tight linewidth → not dispersion limited at 1 Gbps."""
        res = chromatic_dispersion_bandwidth(
            dispersion_ps_per_nm_km=17.0,
            length_km=10.0,
            source_linewidth_nm=0.01,
            bit_rate_bps=1e9,
        )
        assert res["ok"] is True
        assert res["dispersion_limited"] is False

    def test_bw_km_product(self):
        """BW·length product = BW_limit × length."""
        res = chromatic_dispersion_bandwidth(
            dispersion_ps_per_nm_km=17.0,
            length_km=50.0,
            source_linewidth_nm=0.1,
        )
        assert res["ok"] is True
        assert abs(res["bw_km_product_bps_km"] / res["bw_limit_bps"] - 50.0) < 0.01


# =============================================================================
# 15. Modal dispersion bandwidth
# =============================================================================

class TestModalDispersion:
    def test_modal_dispersion_multimode(self):
        """Multimode fiber: NA=0.2, n1=1.46, L=1 km.
        ΔT = NA² × L_m / (2 × n1 × c)
           = 0.04 × 1000 / (2 × 1.46 × 2.998e8)
           ≈ 4.57e-8 s = 45.7 ns
        BW_limit = 0.44 / ΔT ≈ 9.6 MHz."""
        res = modal_dispersion_bandwidth(na=0.2, n1=1.46, length_km=1.0)
        assert res["ok"] is True
        # NA=0.2 is a high-NA fiber; ΔT ≈ 45 ns → BW ≈ 9.6 MHz
        assert 1e6 < res["bw_limit_bps"] < 200e6

    def test_longer_fiber_lower_bandwidth(self):
        """More length → larger ΔT → lower BW."""
        r1 = modal_dispersion_bandwidth(na=0.2, n1=1.46, length_km=1.0)
        r2 = modal_dispersion_bandwidth(na=0.2, n1=1.46, length_km=10.0)
        assert r2["bw_limit_bps"] < r1["bw_limit_bps"]

    def test_na_ge_1_returns_error(self):
        res = modal_dispersion_bandwidth(na=1.0, n1=1.46, length_km=1.0)
        assert res["ok"] is False


# =============================================================================
# 16. Fiber OSNR
# =============================================================================

class TestFiberOSNR:
    def test_single_span_osnr(self):
        """1 span, 0 dBm signal, 5 dB NF EDFA at 1550 nm (193.1 THz), 12.5 GHz BW.
        N_ase = (10^0.5/2) × h × f × B_o ≈ very small → OSNR should be >> 20 dB."""
        res = fiber_osnr(
            p_signal_dbm=0.0,
            nf_amp_db=5.0,
            freq_hz=193.1e12,
            n_spans=1,
        )
        assert res["ok"] is True
        assert res["osnr_db"] > 20.0

    def test_more_spans_lower_osnr(self):
        """More spans → more ASE noise → lower OSNR."""
        r1 = fiber_osnr(p_signal_dbm=0.0, nf_amp_db=5.0, freq_hz=193.1e12, n_spans=1)
        r10 = fiber_osnr(p_signal_dbm=0.0, nf_amp_db=5.0, freq_hz=193.1e12, n_spans=10)
        assert r10["osnr_db"] < r1["osnr_db"]
        # 10 spans → -10 dB relative to 1 span (10*log10(10) = 10 dB)
        assert abs(r10["osnr_db"] - (r1["osnr_db"] - 10.0)) < 0.5

    def test_osnr_invalid_spans(self):
        res = fiber_osnr(p_signal_dbm=0.0, nf_amp_db=5.0, freq_hz=193.1e12, n_spans=0)
        assert res["ok"] is False


# =============================================================================
# 17. C/N and Eb/N0
# =============================================================================

class TestCNAndEbN0:
    def test_cn_basic(self):
        """C/N = P_rx - Noise = -90 dBW - (-120 dBW) = 30 dB."""
        res = cn_ratio_db(p_rx_dbw=-90.0, noise_dbw=-120.0)
        assert res["ok"] is True
        assert abs(res["cn_db"] - 30.0) < 1e-9

    def test_eb_n0_bpsk(self):
        """BPSK: 1 bit/symbol → Eb/N0 = C/N - 10*log10(1) = C/N."""
        res = eb_n0_db(cn_db=20.0, bits_per_symbol=1.0, symbols_per_hz=1.0)
        assert res["ok"] is True
        assert abs(res["eb_n0_db"] - 20.0) < 1e-9

    def test_eb_n0_qpsk(self):
        """QPSK: 2 bits/symbol → Eb/N0 = C/N - 3 dB."""
        res = eb_n0_db(cn_db=20.0, bits_per_symbol=2.0, symbols_per_hz=1.0)
        assert res["ok"] is True
        assert abs(res["eb_n0_db"] - (20.0 - 10.0 * math.log10(2.0))) < 0.01


# =============================================================================
# 18. erfc / Q-function numerical accuracy
# =============================================================================

class TestErfcQFunction:
    def test_erfc_at_zero(self):
        """erfc(0) = 1."""
        assert abs(_erfc(0.0) - 1.0) < 1.5e-7

    def test_erfc_at_one(self):
        """erfc(1) ≈ 0.1573 (tabulated)."""
        assert abs(_erfc(1.0) - 0.15729920705) < 1e-5

    def test_erfc_symmetric(self):
        """erfc(-x) = 2 - erfc(x)."""
        for x in [0.5, 1.0, 2.0, 3.0]:
            assert abs(_erfc(-x) - (2.0 - _erfc(x))) < 1e-10

    def test_q_func_at_zero(self):
        """Q(0) = 0.5."""
        assert abs(_q_func(0.0) - 0.5) < 1.5e-7

    def test_q_func_positive(self):
        """Q(x) decreases as x increases."""
        assert _q_func(1.0) < _q_func(0.0)
        assert _q_func(2.0) < _q_func(1.0)


# =============================================================================
# 19. LLM tool handlers (async smoke tests)
# =============================================================================

class TestLLMTools:
    @pytest.mark.asyncio
    async def test_fspl_tool(self):
        res = await call(_tool_mod.linkbudget_fspl, freq_hz=1e9, distance_m=1000.0)
        assert res["ok"] is True
        assert "fspl_db" in res

    @pytest.mark.asyncio
    async def test_eirp_tool(self):
        res = await call(_tool_mod.linkbudget_eirp, p_tx_dbw=0.0, g_tx_dbi=10.0)
        assert res["ok"] is True
        assert abs(res["eirp_dbw"] - 10.0) < 1e-9

    @pytest.mark.asyncio
    async def test_thermal_noise_tool(self):
        res = await call(_tool_mod.linkbudget_thermal_noise, bandwidth_hz=1e6, temp_k=290.0)
        assert res["ok"] is True
        assert abs(res["noise_dbm"] - (-114.0)) < 0.2

    @pytest.mark.asyncio
    async def test_shannon_tool(self):
        res = await call(_tool_mod.linkbudget_shannon, bandwidth_hz=1.0, snr_db=0.0)
        assert res["ok"] is True
        assert abs(res["capacity_bps"] - 1.0) < 1e-9

    @pytest.mark.asyncio
    async def test_ber_bpsk_tool(self):
        res = await call(_tool_mod.linkbudget_ber_bpsk, eb_n0_db=9.6)
        assert res["ok"] is True
        assert res["ber"] < 1e-4

    @pytest.mark.asyncio
    async def test_rf_budget_tool_passes(self):
        res = await call(
            _tool_mod.linkbudget_rf_budget,
            p_tx_dbw=10.0,
            g_tx_dbi=10.0,
            g_rx_dbi=30.0,
            freq_hz=2.4e9,
            distance_m=100e3,
            noise_figure_db=3.0,
            bandwidth_hz=1e6,
            required_snr_db=10.0,
        )
        assert res["ok"] is True
        assert res["passes"] is True

    @pytest.mark.asyncio
    async def test_fiber_budget_tool(self):
        res = await call(
            _tool_mod.linkbudget_fiber_budget,
            p_tx_dbm=0.0,
            rx_sensitivity_dbm=-30.0,
            fiber_loss_db_per_km=0.35,
            length_km=10.0,
        )
        assert res["ok"] is True
        assert res["passes"] is True

    @pytest.mark.asyncio
    async def test_required_ebn0_tool_bpsk(self):
        res = await call(
            _tool_mod.linkbudget_required_ebn0,
            target_ber=1e-6,
            modulation="BPSK",
        )
        assert res["ok"] is True
        assert 9.0 < res["eb_n0_db"] < 12.0

    @pytest.mark.asyncio
    async def test_tool_invalid_json(self):
        result = await _tool_mod.linkbudget_fspl(None, b"not-valid-json")
        data = json.loads(result)
        # Real kerf_chat err_payload: {"error": ..., "code": ...}
        # Stub err_payload:           {"ok": False, "error": ..., "code": ...}
        # Both indicate error — check that "ok" is not True and "error"/"code" is present
        assert data.get("ok") is not True
        assert "error" in data or "code" in data

    @pytest.mark.asyncio
    async def test_noise_cascade_tool(self):
        res = await call(
            _tool_mod.linkbudget_noise_cascade,
            nf_db_list=[1.5, 8.0],
            gain_db_list=[30.0, 10.0],
        )
        assert res["ok"] is True
        assert res["nf_cascade_db"] < 2.0

    @pytest.mark.asyncio
    async def test_rain_atten_tool(self):
        res = await call(
            _tool_mod.linkbudget_rain_atten,
            freq_hz=10e9,
            rain_rate_mm_per_hr=25.0,
            path_length_km=1.0,
        )
        assert res["ok"] is True
        assert res["a_rain_db"] > 0.0

    @pytest.mark.asyncio
    async def test_fiber_cd_tool(self):
        res = await call(
            _tool_mod.linkbudget_fiber_cd,
            dispersion_ps_per_nm_km=17.0,
            length_km=100.0,
            source_linewidth_nm=0.1,
        )
        assert res["ok"] is True
        assert abs(res["cd_total_ps"] - 170.0) < 0.01

    @pytest.mark.asyncio
    async def test_fiber_osnr_tool(self):
        res = await call(
            _tool_mod.linkbudget_fiber_osnr,
            p_signal_dbm=0.0,
            nf_amp_db=5.0,
            freq_hz=193.1e12,
            n_spans=1,
        )
        assert res["ok"] is True
        assert res["osnr_db"] > 20.0
