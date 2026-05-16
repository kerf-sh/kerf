"""
Hermetic tests for the ADC/DAC data-converter system design module.

Covers ≥ 30 tests:
  ideal_snr
    - 12-bit: SNR = 6.02×12 + 1.76 = 74.0 dB exactly
    - 16-bit: SNR = 6.02×16 + 1.76 = 98.08 dB
    - 8-bit:  SNR = 6.02×8 + 1.76 = 49.92 dB
    - Each bit doubles the noise floor: 1 extra bit → +6.02 dB
    - ok=True with required keys
    - invalid bits (0, 65, string) → ok=False

  snr_with_backoff
    - −6 dB backoff on 12-bit → SNR = 74.0 − 6 = 68.0 dB
    - backoff > 0 → ok=False
    - ENOB decreases with backoff

  enob_from_sinad
    - SINAD = 74.0 dB → ENOB = (74.0 − 1.76)/6.02 ≈ 12.0
    - SINAD = 50.0 dB → ENOB = (50.0 − 1.76)/6.02 ≈ 8.01
    - zero SINAD → ok=False

  snr_sfdr_thd_sinad_interconvert
    - Three metrics given, fourth computed
    - Round-trip: compute SINAD, then recover SNR
    - Fewer than 3 inputs → ok=False
    - Inconsistent inputs detected

  total_noise_budget
    - Quantisation noise = V_fs / (sqrt(6) × 2^N)
    - Jitter SNR = −20log10(2π × f × t_j)
    - kTC noise = sqrt(kT/C)
    - jitter_limited flag triggers when jitter >> quantisation
    - thermal_limited flag when kTC >> quantisation

  oversampling_gain  (Kester, Analog Devices MT-001)
    - OSR=1 → process_gain = 0 dB
    - OSR=4 → process_gain = 10*log10(4) = 6.02 dB (1 ENOB / 4× OSR)
    - OSR=256 → process_gain = 24.08 dB (4 effective bits gained)
    - target_enob triggers osr_required computation
    - osr_insufficient flag when osr_required > 256

  delta_sigma_sqnr  (Schreier & Temes Eq. 2.10)
    - L=1, OSR=64: SQNR ≈ 51 dB (textbook reference value)
    - L=2, OSR=64: SQNR ≈ 79 dB (textbook reference value)
    - Higher order → higher SQNR at same OSR
    - Higher OSR → higher SQNR at same order
    - OSR < 4 → osr_insufficient=True + warning

  sar_conversion_time
    - t_convert = N × (t_comp + t_sw)
    - RC settling = (N+2) × R × C
    - t_total = max(t_convert, t_settle_rc)
    - throughput = 1 / t_total

  pipeline_latency
    - latency_s = num_stages × t_clk_s
    - total_bits = num_stages × bits_per_stage + flash_bits
    - stage_gain = 2^bits_per_stage
    - throughput = 1/t_clk_s

  dac_glitch_sfdr
    - SFDR = −20log10(INL × 2^(1−N))
    - lsb_size = v_fs / 2^N
    - glitch energy = V_glitch × t_glitch

  reference_noise_lsb
    - LSB = V_ref / 2^N exactly
    - SNR_ref depends on e_ref_rms / vn_q ratio
    - drift_lsb = ppm × ΔT × 2^N / 1e6

  adc_driver_settling
    - tau = R × C_in
    - t_settle = (N+2) × tau
    - f_aa = 1/(2π R C_aa) when c_aa_f given

  bits_for_dynamic_range
    - 74 dB DR → 12 bits (ceil((74-1.76)/6.02) = ceil(12.0) = 12)
    - 80 dB DR → ceil((80-1.76)/6.02) = ceil(12.99) = 13 bits
    - achieved SNR ≥ target DR

  LLM tool handlers
    - adc_ideal_snr tool: ok=True
    - adc_enob_from_sinad tool: ok=True
    - adc_oversampling_gain tool: ok=True
    - dac_delta_sigma_sqnr tool: ok=True
    - tool with invalid JSON → error payload

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

from kerf_electronics.dataconv.converters import (
    ideal_snr,
    snr_with_backoff,
    enob_from_sinad,
    snr_sfdr_thd_sinad_interconvert,
    total_noise_budget,
    oversampling_gain,
    delta_sigma_sqnr,
    sar_conversion_time,
    pipeline_latency,
    dac_glitch_sfdr,
    reference_noise_lsb,
    adc_driver_settling,
    bits_for_dynamic_range,
)

# ── Load tool module via importlib so stub is active ─────────────────────────
_tool_spec = importlib.util.spec_from_file_location(
    "kerf_electronics.dataconv.tools",
    os.path.join(_SRC, "kerf_electronics", "dataconv", "tools.py"),
)
_tool_mod = importlib.util.module_from_spec(_tool_spec)
_tool_spec.loader.exec_module(_tool_mod)

_adc_ideal_snr_tool = _tool_mod.adc_ideal_snr
_adc_enob_tool = _tool_mod.adc_enob_from_sinad
_adc_osr_tool = _tool_mod.adc_oversampling_gain
_ds_sqnr_tool = _tool_mod.dac_delta_sigma_sqnr
_bits_dr_tool = _tool_mod.adc_bits_for_dynamic_range
_noise_budget_tool = _tool_mod.adc_total_noise_budget


# ── Async call helper ─────────────────────────────────────────────────────────

async def call(fn, **kwargs):
    result = await fn(None, json.dumps(kwargs).encode())
    return json.loads(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. ideal_snr
# ═══════════════════════════════════════════════════════════════════════════════

class TestIdealSnr:
    def test_12bit_exact(self):
        """12-bit: SNR = 6.02×12 + 1.76 = 74.00 dB."""
        res = ideal_snr(12)
        assert res["ok"] is True
        assert abs(res["snr_ideal_db"] - (6.02 * 12 + 1.76)) < 0.01

    def test_16bit_exact(self):
        """16-bit: SNR = 6.02×16 + 1.76 = 98.08 dB."""
        res = ideal_snr(16)
        assert res["ok"] is True
        assert abs(res["snr_ideal_db"] - (6.02 * 16 + 1.76)) < 0.01

    def test_8bit_exact(self):
        """8-bit: SNR = 6.02×8 + 1.76 = 49.92 dB."""
        res = ideal_snr(8)
        assert res["ok"] is True
        assert abs(res["snr_ideal_db"] - (6.02 * 8 + 1.76)) < 0.01

    def test_one_bit_increase_gives_6_02_db(self):
        """Each additional bit adds exactly 6.02 dB (within floating-point precision)."""
        r8 = ideal_snr(8)
        r9 = ideal_snr(9)
        assert abs((r9["snr_ideal_db"] - r8["snr_ideal_db"]) - 6.02) < 1e-6

    def test_returns_required_keys(self):
        res = ideal_snr(10)
        assert res["ok"] is True
        for key in ("bits", "snr_ideal_db", "dynamic_range_db"):
            assert key in res

    def test_invalid_bits_zero(self):
        res = ideal_snr(0)
        assert res["ok"] is False

    def test_invalid_bits_too_large(self):
        res = ideal_snr(65)
        assert res["ok"] is False

    def test_invalid_bits_string(self):
        res = ideal_snr("12")  # type: ignore
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 2. snr_with_backoff
# ═══════════════════════════════════════════════════════════════════════════════

class TestSnrWithBackoff:
    def test_6db_backoff_on_12bit(self):
        """−6 dB backoff: SNR_actual = 74.00 − 6 = 68.00 dB."""
        res = snr_with_backoff(12, -6.0)
        assert res["ok"] is True
        assert abs(res["snr_actual_db"] - (6.02 * 12 + 1.76 - 6.0)) < 0.01

    def test_zero_backoff_equals_ideal(self):
        """0 dB backoff: SNR_actual == SNR_ideal."""
        res = snr_with_backoff(12, 0.0)
        assert res["ok"] is True
        assert abs(res["snr_actual_db"] - res["snr_ideal_db"]) < 1e-9

    def test_backoff_positive_returns_error(self):
        """Positive backoff is invalid (input above full scale)."""
        res = snr_with_backoff(12, 3.0)
        assert res["ok"] is False

    def test_enob_decreases_with_backoff(self):
        """More backoff → lower ENOB."""
        r0 = snr_with_backoff(12, 0.0)
        r6 = snr_with_backoff(12, -6.0)
        assert r6["enob_actual"] < r0["enob_actual"]


# ═══════════════════════════════════════════════════════════════════════════════
# 3. enob_from_sinad
# ═══════════════════════════════════════════════════════════════════════════════

class TestEnobFromSinad:
    def test_12bit_sinad_roundtrip(self):
        """12-bit ideal SNR as SINAD should return ENOB ≈ 12."""
        sinad = 6.02 * 12 + 1.76
        res = enob_from_sinad(sinad)
        assert res["ok"] is True
        assert abs(res["enob"] - 12.0) < 1e-3

    def test_50db_sinad(self):
        """SINAD = 50.0 dB → ENOB = (50.0 − 1.76) / 6.02 ≈ 8.01."""
        res = enob_from_sinad(50.0)
        assert res["ok"] is True
        assert abs(res["enob"] - (50.0 - 1.76) / 6.02) < 1e-3

    def test_zero_sinad_returns_error(self):
        res = enob_from_sinad(0.0)
        assert res["ok"] is False

    def test_negative_sinad_returns_error(self):
        res = enob_from_sinad(-10.0)
        assert res["ok"] is False

    def test_required_keys_present(self):
        res = enob_from_sinad(60.0)
        for key in ("sinad_db", "enob", "implied_ideal_bits"):
            assert key in res


# ═══════════════════════════════════════════════════════════════════════════════
# 4. snr_sfdr_thd_sinad_interconvert
# ═══════════════════════════════════════════════════════════════════════════════

class TestInterconvert:
    def test_compute_sinad_from_three(self):
        """Given SNR=70, SFDR=80, THD=−65: compute SINAD."""
        res = snr_sfdr_thd_sinad_interconvert(
            snr_db=70.0, sfdr_dbc=80.0, thd_dbc=-65.0
        )
        assert res["ok"] is True
        # Verify SINAD manually
        expected = -10.0 * math.log10(
            10.0 ** (-70.0 / 10.0)
            + 10.0 ** (-80.0 / 10.0)
            + 10.0 ** (-65.0 / 10.0)
        )
        assert abs(res["sinad_db"] - expected) < 0.01

    def test_roundtrip_snr(self):
        """Compute SINAD from (SNR, SFDR, THD), then recover SNR."""
        r1 = snr_sfdr_thd_sinad_interconvert(
            snr_db=72.0, sfdr_dbc=85.0, thd_dbc=-70.0
        )
        assert r1["ok"] is True
        r2 = snr_sfdr_thd_sinad_interconvert(
            sfdr_dbc=85.0, thd_dbc=-70.0, sinad_db=r1["sinad_db"]
        )
        assert r2["ok"] is True
        assert abs(r2["snr_db"] - 72.0) < 0.01

    def test_fewer_than_three_inputs_error(self):
        res = snr_sfdr_thd_sinad_interconvert(snr_db=70.0, sfdr_dbc=80.0)
        assert res["ok"] is False

    def test_enob_computed_from_sinad(self):
        """ENOB = (SINAD − 1.76) / 6.02 always holds (within rounding)."""
        res = snr_sfdr_thd_sinad_interconvert(
            snr_db=68.0, sfdr_dbc=78.0, thd_dbc=-60.0
        )
        assert res["ok"] is True
        expected_enob = (res["sinad_db"] - 1.76) / 6.02
        assert abs(res["enob"] - expected_enob) < 1e-3


# ═══════════════════════════════════════════════════════════════════════════════
# 5. total_noise_budget
# ═══════════════════════════════════════════════════════════════════════════════

class TestTotalNoiseBudget:
    def test_quantisation_noise_formula(self):
        """vn_q = V_fs / (sqrt(6) × 2^N)."""
        bits, v_fs = 12, 2.0
        res = total_noise_budget(
            bits=bits, v_fs=v_fs, freq_in_hz=1e3, t_jitter_s=1e-12,
            cap_dac_f=10e-12
        )
        assert res["ok"] is True
        expected_vn_q = v_fs / (math.sqrt(6.0) * (2 ** bits))
        assert abs(res["vn_q_vrms"] - expected_vn_q) < expected_vn_q * 1e-9

    def test_ktc_noise_formula(self):
        """vn_ktc = sqrt(kT/C)."""
        C = 1e-12
        k = 1.381e-23
        T = 300.0
        res = total_noise_budget(
            bits=16, v_fs=3.3, freq_in_hz=1e3, t_jitter_s=1e-15,
            cap_dac_f=C, temp_k=T
        )
        expected = math.sqrt(k * T / C)
        assert abs(res["vn_ktc_vrms"] - expected) < expected * 1e-6

    def test_jitter_snr_formula(self):
        """SNR_jitter = −20log10(2π × f_in × t_j)."""
        f, tj = 1e6, 1e-12
        res = total_noise_budget(
            bits=16, v_fs=2.0, freq_in_hz=f, t_jitter_s=tj, cap_dac_f=10e-12
        )
        expected_jitter_snr = -20.0 * math.log10(2.0 * math.pi * f * tj)
        assert abs(res["snr_jitter_db"] - expected_jitter_snr) < 0.01

    def test_jitter_limited_flag(self):
        """High jitter → jitter_limited=True + warning."""
        # t_jitter = 100 ps at 100 MHz → SNR_jitter ≈ −20log10(2π×100e6×100e-12) ≈ 24 dB
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = total_noise_budget(
                bits=16, v_fs=2.0, freq_in_hz=100e6, t_jitter_s=100e-12,
                cap_dac_f=10e-12
            )
            assert res["jitter_limited"] is True
            assert any("jitter" in str(x.message).lower() for x in w)

    def test_thermal_limited_flag(self):
        """Very small cap → kTC >> quantisation → thermal_limited=True."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = total_noise_budget(
                bits=16, v_fs=2.0, freq_in_hz=1e3, t_jitter_s=1e-15,
                cap_dac_f=0.001e-12,  # 1 fF — tiny cap, huge kTC
                temp_k=300.0
            )
            assert res["thermal_limited"] is True
            assert any("thermal" in str(x.message).lower() for x in w)

    def test_required_keys_present(self):
        res = total_noise_budget(
            bits=12, v_fs=3.3, freq_in_hz=1e6, t_jitter_s=1e-12, cap_dac_f=1e-12
        )
        assert res["ok"] is True
        for key in ("vn_q_vrms", "vn_ktc_vrms", "snr_jitter_db", "vn_total_vrms",
                    "snr_total_db", "dominant_noise"):
            assert key in res

    def test_invalid_v_fs_returns_error(self):
        res = total_noise_budget(bits=12, v_fs=-1.0, freq_in_hz=1e3, t_jitter_s=1e-12)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 6. oversampling_gain
# ═══════════════════════════════════════════════════════════════════════════════

class TestOversamplingGain:
    def test_osr_1_zero_gain(self):
        """OSR=1 → process gain = 0 dB."""
        res = oversampling_gain(bits=12, osr=1.0)
        assert res["ok"] is True
        assert abs(res["process_gain_db"]) < 1e-9

    def test_osr_4_gives_6db(self):
        """OSR=4 → process gain = 10*log10(4) ≈ 6.02 dB (1 ENOB / 4× OSR).

        Kester, Analog Devices MT-001 "Taking the Mystery out of the
        Infamous Formula": oversampling without noise shaping improves
        SNR by 10·log10(OSR) dB; a 4× OSR buys exactly 6.02 dB ≈ 1 bit.
        """
        res = oversampling_gain(bits=12, osr=4.0)
        assert res["ok"] is True
        expected = 10.0 * math.log10(4.0)  # 6.0206 dB
        assert abs(res["process_gain_db"] - expected) < 0.01
        assert abs(res["process_gain_db"] - 6.0206) < 0.01

    def test_osr_256_gives_24db(self):
        """OSR=256 → process gain = 10*log10(256) ≈ 24.08 dB (4 ENOB).

        Kester MT-001: 256× OSR = 4 doublings-of-4 = 4 bits = 24.08 dB.
        """
        res = oversampling_gain(bits=12, osr=256.0)
        expected = 10.0 * math.log10(256.0)  # 24.08 dB
        assert abs(res["process_gain_db"] - expected) < 0.01
        assert abs(res["process_gain_db"] - 24.082) < 0.01

    def test_target_enob_gives_osr_required(self):
        """target_enob forces osr_required computation."""
        res = oversampling_gain(bits=12, osr=1.0, target_enob=14.0)
        assert res["ok"] is True
        assert "osr_required" in res
        # 2 extra ENOB from 12-bit → OSR = 4^2 = 16
        assert abs(res["osr_required"] - 16.0) < 0.5

    def test_osr_insufficient_flag(self):
        """Needing more than 256× OSR triggers osr_insufficient flag."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # 8-bit → 20-bit ENOB requires OSR = 4^12 = 16_777_216
            res = oversampling_gain(bits=8, osr=1.0, target_enob=20.0)
            assert res["osr_insufficient"] is True
            assert any("osr" in str(x.message).lower() or
                       "insufficient" in str(x.message).lower() for x in w)

    def test_snr_increases_with_osr(self):
        """Higher OSR → higher SNR."""
        r1 = oversampling_gain(bits=12, osr=4.0)
        r2 = oversampling_gain(bits=12, osr=16.0)
        assert r2["snr_with_osr_db"] > r1["snr_with_osr_db"]


# ═══════════════════════════════════════════════════════════════════════════════
# 7. delta_sigma_sqnr
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeltaSigmaSqnr:
    def test_first_order_osr64(self):
        """L=1, OSR=64: verify Schreier & Temes Eq. 2.10 numerically.

        Schreier & Temes, "Understanding Delta-Sigma Data Converters"
        (2005) Eq. 2.10:  SQNR = 10log10[(2L+1)/π^(2L)]
                                  + (20L+10)log10(OSR) + 1.76.
        Textbook reference: 1st-order, OSR=64 → ≈ 51 dB (≈8 ENOB).
        """
        L, osr = 1, 64.0
        res = delta_sigma_sqnr(L, osr)
        assert res["ok"] is True
        expected = (
            10.0 * math.log10((2 * L + 1) / (math.pi ** (2 * L)))
            + (20 * L + 10) * math.log10(osr)
            + 1.76
        )
        assert abs(res["sqnr_db"] - expected) < 0.01
        # Sanity vs textbook reference value (≈51 dB, ≈8 ENOB)
        assert 49.0 < res["sqnr_db"] < 53.0

    def test_second_order_osr64_reference(self):
        """L=2, OSR=64 → ≈ 79 dB (≈13 ENOB) — canonical textbook value.

        Schreier & Temes 2005 / Pavan-Schreier-Temes 2nd ed.: the
        oft-quoted "2nd-order ΔΣ, OSR=64 ≈ 80 dB / 13 bits" result.
        """
        res = delta_sigma_sqnr(2, 64.0)
        assert res["ok"] is True
        assert 77.0 < res["sqnr_db"] < 81.0
        assert 12.5 < res["enob_equivalent"] < 13.3

    def test_higher_order_higher_sqnr(self):
        """L=2 gives higher SQNR than L=1 at same OSR."""
        r1 = delta_sigma_sqnr(1, 64.0)
        r2 = delta_sigma_sqnr(2, 64.0)
        assert r2["sqnr_db"] > r1["sqnr_db"]

    def test_higher_osr_higher_sqnr(self):
        """Doubling OSR increases SQNR."""
        r1 = delta_sigma_sqnr(2, 64.0)
        r2 = delta_sigma_sqnr(2, 128.0)
        assert r2["sqnr_db"] > r1["sqnr_db"]

    def test_low_osr_flag(self):
        """OSR < 4 triggers osr_insufficient=True and warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = delta_sigma_sqnr(1, 2.0)
            assert res["osr_insufficient"] is True
            assert any("osr" in str(x.message).lower() for x in w)

    def test_enob_consistent_with_sqnr(self):
        """ENOB = (SQNR − 1.76) / 6.02 (within rounding)."""
        res = delta_sigma_sqnr(3, 64.0)
        expected_enob = (res["sqnr_db"] - 1.76) / 6.02
        assert abs(res["enob_equivalent"] - expected_enob) < 1e-3

    def test_invalid_order_returns_error(self):
        res = delta_sigma_sqnr(0, 64.0)
        assert res["ok"] is False

    def test_invalid_osr_returns_error(self):
        res = delta_sigma_sqnr(2, 0.5)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 8. sar_conversion_time
# ═══════════════════════════════════════════════════════════════════════════════

class TestSarConversionTime:
    def test_basic_conversion_time(self):
        """t_convert = N × (t_comp + t_sw)."""
        bits, tc, ts = 12, 5e-9, 3e-9
        res = sar_conversion_time(bits, tc, ts)
        assert res["ok"] is True
        expected = bits * (tc + ts)
        assert abs(res["t_compare_s"] - expected) < 1e-18

    def test_rc_settling_included(self):
        """t_settle_rc = (N+2) × R × C."""
        bits, tc, ts = 12, 5e-9, 3e-9
        R, C = 100.0, 1e-12
        res = sar_conversion_time(bits, tc, ts, r_src_ohm=R, c_dac_f=C)
        expected_rc = (bits + 2) * R * C
        assert abs(res["t_settle_rc_s"] - expected_rc) < 1e-18

    def test_total_is_max(self):
        """t_total = max(t_compare, t_settle_rc)."""
        bits, tc, ts = 12, 1e-9, 1e-9
        R, C = 1e6, 1e-12  # large R → RC-dominated
        res = sar_conversion_time(bits, tc, ts, r_src_ohm=R, c_dac_f=C)
        assert abs(res["t_total_s"] - max(res["t_compare_s"], res["t_settle_rc_s"])) < 1e-18

    def test_throughput_from_total(self):
        """throughput = 1 / t_total."""
        res = sar_conversion_time(12, 5e-9, 3e-9)
        assert abs(res["throughput_max_sps"] - 1.0 / res["t_total_s"]) < 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# 9. pipeline_latency
# ═══════════════════════════════════════════════════════════════════════════════

class TestPipelineLatency:
    def test_latency_formula(self):
        """latency_s = num_stages × t_clk_s."""
        res = pipeline_latency(num_stages=10, bits_per_stage=2, t_clk_s=5e-9)
        assert res["ok"] is True
        assert abs(res["latency_s"] - 10 * 5e-9) < 1e-18

    def test_total_bits(self):
        """total_bits = num_stages × bits_per_stage + flash_bits."""
        res = pipeline_latency(num_stages=6, bits_per_stage=2, t_clk_s=1e-9, flash_bits=3)
        assert res["total_bits_nominal"] == 6 * 2 + 3

    def test_stage_gain(self):
        """stage_gain = 2^bits_per_stage."""
        res = pipeline_latency(num_stages=8, bits_per_stage=3, t_clk_s=2e-9)
        assert res["stage_gain"] == 2 ** 3

    def test_throughput_equals_clock_rate(self):
        """Pipeline throughput = 1/t_clk (one sample per clock after fill)."""
        t_clk = 4e-9
        res = pipeline_latency(num_stages=8, bits_per_stage=2, t_clk_s=t_clk)
        assert abs(res["throughput_sps"] - 1.0 / t_clk) < 1.0

    def test_invalid_num_stages(self):
        res = pipeline_latency(num_stages=0, bits_per_stage=2, t_clk_s=1e-9)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 10. dac_glitch_sfdr
# ═══════════════════════════════════════════════════════════════════════════════

class TestDacGlitchSfdr:
    def test_sfdr_formula(self):
        """SFDR = −20log10(INL × 2^(1−N)) for 12-bit, 0.5 LSB INL."""
        bits, inl = 12, 0.5
        res = dac_glitch_sfdr(bits, inl, 2.0, 0.01, 1e-9, 1e-9)
        expected = -20.0 * math.log10(inl * 2 ** (1 - bits))
        assert res["ok"] is True
        assert abs(res["sfdr_dbc"] - expected) < 0.01

    def test_lsb_size_formula(self):
        """lsb_size = V_fs / 2^N."""
        bits, v_fs = 12, 2.0
        res = dac_glitch_sfdr(bits, 0.5, v_fs, 0.01, 1e-9, 1e-9)
        assert abs(res["lsb_size_v"] - v_fs / (2 ** bits)) < 1e-12

    def test_glitch_energy(self):
        """Glitch energy = V_glitch × t_glitch."""
        vg, tg = 0.05, 2e-9
        res = dac_glitch_sfdr(12, 0.5, 2.0, vg, tg, 1e-9)
        assert abs(res["e_glitch_vs"] - vg * tg) < 1e-18

    def test_higher_inl_lower_sfdr(self):
        """Larger INL → worse (lower) SFDR."""
        r1 = dac_glitch_sfdr(12, 0.5, 2.0, 0.01, 1e-9, 1e-9)
        r2 = dac_glitch_sfdr(12, 2.0, 2.0, 0.01, 1e-9, 1e-9)
        assert r2["sfdr_dbc"] < r1["sfdr_dbc"]


# ═══════════════════════════════════════════════════════════════════════════════
# 11. reference_noise_lsb
# ═══════════════════════════════════════════════════════════════════════════════

class TestReferenceNoiseLsb:
    def test_lsb_size(self):
        """lsb_v = V_ref / 2^N exactly."""
        bits, v_ref = 12, 4.096
        res = reference_noise_lsb(bits, v_ref, 1e-6)
        assert res["ok"] is True
        assert abs(res["lsb_v"] - v_ref / (2 ** bits)) < 1e-12

    def test_drift_zero_when_params_zero(self):
        """No drift parameters → drift_error_lsb = 0."""
        res = reference_noise_lsb(12, 2.5, 1e-7, drift_ppm_per_c=0.0, delta_temp_c=0.0)
        assert abs(res["drift_error_lsb"]) < 1e-9

    def test_drift_formula(self):
        """drift_lsb = ppm × ΔT × 2^N / 1e6."""
        bits, ppm, dt = 12, 10.0, 50.0
        res = reference_noise_lsb(bits, 2.5, 1e-7, drift_ppm_per_c=ppm, delta_temp_c=dt)
        expected = ppm * dt * (2 ** bits) / 1e6
        assert abs(res["drift_error_lsb"] - expected) < 1e-6

    def test_snr_ref_decreases_with_higher_noise(self):
        """Higher reference noise → lower SNR_ref."""
        r1 = reference_noise_lsb(12, 2.5, 1e-7)
        r2 = reference_noise_lsb(12, 2.5, 1e-5)
        assert r2["snr_ref_db"] < r1["snr_ref_db"]


# ═══════════════════════════════════════════════════════════════════════════════
# 12. adc_driver_settling
# ═══════════════════════════════════════════════════════════════════════════════

class TestAdcDriverSettling:
    def test_tau_formula(self):
        """τ = R × C_in."""
        R, C = 100.0, 5e-12
        res = adc_driver_settling(12, R, C)
        assert res["ok"] is True
        assert abs(res["tau_s"] - R * C) < 1e-20

    def test_settle_time_formula(self):
        """t_settle = (N + 2) × τ."""
        bits, R, C = 12, 100.0, 5e-12
        res = adc_driver_settling(bits, R, C)
        expected = (bits + 2) * R * C
        assert abs(res["t_settle_s"] - expected) < 1e-20

    def test_aa_filter_frequency(self):
        """f_aa = 1/(2π × R × C_aa)."""
        R, C_aa = 1000.0, 10e-12
        res = adc_driver_settling(12, R, 5e-12, c_aa_f=C_aa)
        expected_faa = 1.0 / (2.0 * math.pi * R * C_aa)
        assert abs(res["f_aa_3db_hz"] - expected_faa) / expected_faa < 1e-9

    def test_no_aa_gives_none(self):
        """Without c_aa_f, f_aa_3db_hz = None."""
        res = adc_driver_settling(12, 100.0, 5e-12)
        assert res["f_aa_3db_hz"] is None
        assert res["t_settle_aa_s"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# 13. bits_for_dynamic_range
# ═══════════════════════════════════════════════════════════════════════════════

class TestBitsForDynamicRange:
    def test_74db_gives_12_bits(self):
        """74 dB DR: ceil((74 − 1.76) / 6.02) = ceil(12.0) = 12."""
        res = bits_for_dynamic_range(74.0)
        assert res["ok"] is True
        assert res["bits_min"] == 12

    def test_80db_gives_13_bits(self):
        """80 dB DR: ceil((80 − 1.76) / 6.02) = ceil(12.99…) = 13."""
        res = bits_for_dynamic_range(80.0)
        assert res["ok"] is True
        assert res["bits_min"] == 13

    def test_achieved_snr_meets_target(self):
        """Achieved SNR ≥ target DR for any input."""
        for dr in [50.0, 75.0, 96.0, 120.0]:
            res = bits_for_dynamic_range(dr)
            assert res["ok"] is True
            assert res["snr_achieved_db"] >= dr - 0.01

    def test_margin_nonneg(self):
        """margin_db = snr_achieved − dr_target ≥ 0."""
        res = bits_for_dynamic_range(60.0)
        assert res["margin_db"] >= -0.01

    def test_invalid_dr_returns_error(self):
        res = bits_for_dynamic_range(-10.0)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 14. LLM tool handlers (stub registry)
# ═══════════════════════════════════════════════════════════════════════════════

class TestToolHandlers:
    @pytest.mark.asyncio
    async def test_adc_ideal_snr_tool_ok(self):
        res = await call(_adc_ideal_snr_tool, bits=12)
        assert res["ok"] is True
        assert "snr_ideal_db" in res

    @pytest.mark.asyncio
    async def test_adc_enob_tool_ok(self):
        res = await call(_adc_enob_tool, sinad_db=74.0)
        assert res["ok"] is True
        assert "enob" in res

    @pytest.mark.asyncio
    async def test_adc_osr_tool_ok(self):
        res = await call(_adc_osr_tool, bits=12, osr=16.0)
        assert res["ok"] is True
        assert "process_gain_db" in res

    @pytest.mark.asyncio
    async def test_ds_sqnr_tool_ok(self):
        res = await call(_ds_sqnr_tool, order=2, osr=64.0)
        assert res["ok"] is True
        assert "sqnr_db" in res

    @pytest.mark.asyncio
    async def test_bits_dr_tool_ok(self):
        res = await call(_bits_dr_tool, dr_db=90.0)
        assert res["ok"] is True
        assert "bits_min" in res

    @pytest.mark.asyncio
    async def test_noise_budget_tool_ok(self):
        res = await call(
            _noise_budget_tool,
            bits=12, v_fs=2.0, freq_in_hz=1e6, t_jitter_s=1e-12, cap_dac_f=1e-12
        )
        assert res["ok"] is True
        assert "snr_total_db" in res

    @pytest.mark.asyncio
    async def test_tool_invalid_json_returns_error(self):
        result = await _adc_ideal_snr_tool(None, b"not valid json{{")
        data = json.loads(result)
        assert data.get("ok") is False or "error" in data

    @pytest.mark.asyncio
    async def test_adc_ideal_snr_bad_bits_returns_error(self):
        result = await _adc_ideal_snr_tool(
            None, json.dumps({"bits": 0}).encode()
        )
        data = json.loads(result)
        assert data.get("ok") is False or "error" in data


# ═══════════════════════════════════════════════════════════════════════════════
# Externally-citable reference cases (authoritative published numbers)
# ═══════════════════════════════════════════════════════════════════════════════

class TestExternalReferenceCases:
    """Each case cross-checks an output against a numeric value published in
    a citable source.  Tolerances reflect the precision quoted in the source.
    """

    def test_ref_kester_mt001_12bit_snr_74db(self):
        # Kester, Analog Devices MT-001, Eq. 1: 12-bit ideal SNR = 74 dB.
        r = ideal_snr(12)
        assert abs(r["snr_ideal_db"] - 74.0) < 0.05  # 6.02·12+1.76 = 74.0

    def test_ref_kester_mt001_16bit_snr_98db(self):
        # Kester MT-001: 16-bit ideal SNR = 98.08 dB (≈98 dB quoted).
        r = ideal_snr(16)
        assert abs(r["snr_ideal_db"] - 98.08) < 0.05

    def test_ref_kester_mt001_8bit_snr_50db(self):
        # Kester MT-001: 8-bit ideal SNR = 49.92 dB (≈50 dB quoted).
        r = ideal_snr(8)
        assert abs(r["snr_ideal_db"] - 49.92) < 0.05

    def test_ref_ieee1241_enob_from_sinad(self):
        # IEEE Std 1241-2010 §3.1.7: SINAD = 74 dB → ENOB = 12.00 bits.
        r = enob_from_sinad(74.0)
        assert abs(r["enob"] - 12.0) < 0.01

    def test_ref_kester_mt001_osr_4x_one_bit(self):
        # Kester MT-001: oversampling without noise shaping — 4× OSR buys
        # exactly 6.02 dB ≈ 1 ENOB. (NO /2 factor.)
        r = oversampling_gain(bits=12, osr=4.0)
        assert abs(r["process_gain_db"] - 6.0206) < 0.01
        assert abs(r["enob_with_osr"] - 13.0) < 0.01  # 12 + 1

    def test_ref_kester_mt001_osr_factor_for_2bits(self):
        # Kester MT-001: gaining N effective bits needs OSR = 4^N.
        # 2 extra ENOB from a 12-bit ADC → OSR = 16.
        r = oversampling_gain(bits=12, osr=1.0, target_enob=14.0)
        assert abs(r["osr_required"] - 16.0) < 0.5

    def test_ref_schreier_temes_l1_osr64_51db(self):
        # Schreier & Temes, "Understanding Delta-Sigma Data Converters"
        # (2005) Eq. 2.10: 1st-order ΔΣ, OSR=64 → ≈51 dB SQNR.
        r = delta_sigma_sqnr(1, 64.0)
        assert abs(r["sqnr_db"] - 50.8) < 1.0

    def test_ref_schreier_temes_l2_osr64_79db(self):
        # Schreier & Temes 2005 / Pavan-Schreier-Temes 2nd ed.: the
        # canonical "2nd-order ΔΣ, OSR=64 ≈ 80 dB ≈ 13 bit" datum.
        r = delta_sigma_sqnr(2, 64.0)
        assert abs(r["sqnr_db"] - 79.2) < 1.0
        assert abs(r["enob_equivalent"] - 12.86) < 0.2

    def test_ref_schreier_temes_l3_osr64_107db(self):
        # Schreier & Temes 2005 Eq. 2.10: 3rd-order ΔΣ, OSR=64 → ≈107 dB.
        r = delta_sigma_sqnr(3, 64.0)
        assert abs(r["sqnr_db"] - 106.8) < 1.5

    def test_ref_schreier_temes_l2_osr128_94db(self):
        # Schreier & Temes 2005 Eq. 2.10: 2nd-order, OSR=128 → ≈94 dB
        # (doubling OSR adds (20·2+10)·log10(2) = 15.05 dB over OSR=64).
        r64 = delta_sigma_sqnr(2, 64.0)
        r128 = delta_sigma_sqnr(2, 128.0)
        assert abs((r128["sqnr_db"] - r64["sqnr_db"]) - 15.05) < 0.1
        assert abs(r128["sqnr_db"] - 94.25) < 1.0

    def test_ref_bennett_dynamic_range_to_bits(self):
        # Bennett 1948 / Kester MT-001 inverse: 90 dB DR needs
        # N = ceil((90−1.76)/6.02) = ceil(14.66) = 15 bits.
        r = bits_for_dynamic_range(90.0)
        assert r["bits_min"] == 15

    def test_ref_ktc_noise_1pf_300k_64uv(self):
        # Johnson-Nyquist kTC sampling-cap noise: sqrt(kT/C) with
        # C=1 pF, T=300 K → 64.4 µV_rms (standard ADC-driver result,
        # e.g. Kester "Data Conversion Handbook" §2, ADI MT-090).
        import warnings as _w
        with _w.catch_warnings():
            _w.simplefilter("ignore")
            r = total_noise_budget(
                bits=16, v_fs=2.0, freq_in_hz=1e3, t_jitter_s=1e-15,
                cap_dac_f=1e-12, temp_k=300.0,
            )
        assert abs(r["vn_ktc_vrms"] * 1e6 - 64.4) < 0.5
