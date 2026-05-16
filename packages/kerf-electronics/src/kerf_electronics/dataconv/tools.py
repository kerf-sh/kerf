"""
ADC/DAC data-converter system design — LLM tools.

Exposes tools to the Kerf agent layer:

  adc_ideal_snr                 — ideal SNR (6.02N+1.76) for N-bit ADC
  adc_snr_with_backoff          — SNR with full-scale input backoff
  adc_enob_from_sinad           — ENOB from measured SINAD
  adc_interconvert_metrics      — SNR/SFDR/THD/SINAD interconversion
  adc_total_noise_budget        — RSS noise budget (quantisation + kTC + jitter + amp)
  adc_oversampling_gain         — oversampling process gain and required OSR
  dac_delta_sigma_sqnr          — ΔΣ modulator order vs OSR → SQNR + noise-shaping
  adc_sar_conversion_time       — SAR conversion time (comparator + RC settling)
  adc_pipeline_latency          — pipeline ADC latency and stage scaling
  dac_glitch_sfdr               — DAC glitch/settling and SFDR from INL
  adc_reference_noise           — reference noise/drift contribution to LSB
  adc_driver_settling           — driver + RC anti-alias kickback settling
  adc_bits_for_dynamic_range    — required bits for a target dynamic range

All handlers follow the kerf never-raise contract:
  Success: {"ok": True, ...}  via ok_payload
  Failure: {"ok": False, "error": ..., "code": ...}  via err_payload
  Never raise.

Author: imranparuk
"""
from __future__ import annotations

import json
from typing import Any

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register

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


# ═══════════════════════════════════════════════════════════════════════════════
# 1. adc_ideal_snr
# ═══════════════════════════════════════════════════════════════════════════════

_IDEAL_SNR_SPEC = ToolSpec(
    name="adc_ideal_snr",
    description=(
        "Compute the ideal ADC SNR for an N-bit full-scale sine wave input.\n\n"
        "Bennett (1948): SNR_ideal [dB] = 6.02 × N + 1.76\n\n"
        "Input: { bits }\n"
        "Returns: { ok, bits, snr_ideal_db, dynamic_range_db }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "bits": {
                "type": "integer",
                "description": "ADC resolution [bits] (1–64).",
                "minimum": 1,
                "maximum": 64,
            },
        },
        "required": ["bits"],
    },
)


@register(_IDEAL_SNR_SPEC, write=False)
async def adc_ideal_snr(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = ideal_snr(bits=a.get("bits"))
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. adc_snr_with_backoff
# ═══════════════════════════════════════════════════════════════════════════════

_SNR_BACKOFF_SPEC = ToolSpec(
    name="adc_snr_with_backoff",
    description=(
        "ADC SNR with full-scale input backoff.\n\n"
        "SNR_actual = SNR_ideal + backoff_db\n"
        "backoff_db ≤ 0 (e.g. −6 dB for half-scale input).\n\n"
        "Input: { bits, backoff_db }\n"
        "Returns: { ok, bits, backoff_db, snr_ideal_db, snr_actual_db, enob_actual }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "bits": {
                "type": "integer",
                "description": "ADC resolution [bits].",
                "minimum": 1,
                "maximum": 64,
            },
            "backoff_db": {
                "type": "number",
                "description": "Input backoff below full scale [dB] (≤ 0).",
            },
        },
        "required": ["bits", "backoff_db"],
    },
)


@register(_SNR_BACKOFF_SPEC, write=False)
async def adc_snr_with_backoff(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = snr_with_backoff(bits=a.get("bits"), backoff_db=a.get("backoff_db"))
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. adc_enob_from_sinad
# ═══════════════════════════════════════════════════════════════════════════════

_ENOB_SINAD_SPEC = ToolSpec(
    name="adc_enob_from_sinad",
    description=(
        "Compute ENOB (Effective Number of Bits) from measured SINAD.\n\n"
        "IEEE Std 1241-2010: ENOB = (SINAD_dB − 1.76) / 6.02\n\n"
        "Input: { sinad_db }\n"
        "Returns: { ok, sinad_db, enob, implied_ideal_bits }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "sinad_db": {
                "type": "number",
                "description": "Measured SINAD [dB] (positive number).",
            },
        },
        "required": ["sinad_db"],
    },
)


@register(_ENOB_SINAD_SPEC, write=False)
async def adc_enob_from_sinad(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = enob_from_sinad(sinad_db=a.get("sinad_db"))
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. adc_interconvert_metrics
# ═══════════════════════════════════════════════════════════════════════════════

_INTERCONVERT_SPEC = ToolSpec(
    name="adc_interconvert_metrics",
    description=(
        "Interconvert ADC/DAC spectral performance metrics: SNR, SFDR, THD, SINAD.\n\n"
        "Walden (1999): SINAD = −10log10( 10^(−SNR/10) + 10^(−SFDR/10) + 10^(THD/10) )\n\n"
        "Provide exactly 3 of the 4 metrics; the fourth is computed.\n"
        "Note: thd_dbc is negative (e.g. −60 dBc), sfdr_dbc is positive.\n\n"
        "Input: { snr_db?, sfdr_dbc?, thd_dbc?, sinad_db? } (any 3 of 4)\n"
        "Returns: { ok, snr_db, sfdr_dbc, thd_dbc, sinad_db, enob }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "snr_db": {
                "type": "number",
                "description": "Signal-to-noise ratio [dB] (noise only, no harmonics).",
            },
            "sfdr_dbc": {
                "type": "number",
                "description": "Spurious-free dynamic range [dBc] (positive).",
            },
            "thd_dbc": {
                "type": "number",
                "description": "Total harmonic distortion [dBc] (negative, e.g. −60).",
            },
            "sinad_db": {
                "type": "number",
                "description": "Signal-to-noise-and-distortion ratio [dB].",
            },
        },
        "required": [],
    },
)


@register(_INTERCONVERT_SPEC, write=False)
async def adc_interconvert_metrics(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = snr_sfdr_thd_sinad_interconvert(
        snr_db=a.get("snr_db"),
        sfdr_dbc=a.get("sfdr_dbc"),
        thd_dbc=a.get("thd_dbc"),
        sinad_db=a.get("sinad_db"),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. adc_total_noise_budget
# ═══════════════════════════════════════════════════════════════════════════════

_NOISE_BUDGET_SPEC = ToolSpec(
    name="adc_total_noise_budget",
    description=(
        "Compute total ADC noise budget: quantisation + kTC thermal + aperture-jitter "
        "+ input-referred amplifier noise, combined as RSS.\n\n"
        "Flags via warnings: jitter-limited / under-resolved / thermal-limited.\n\n"
        "Input: { bits, v_fs, freq_in_hz, t_jitter_s, cap_dac_f?, en_amp_v_per_rtHz?, "
        "bw_hz?, temp_k? }\n"
        "Returns: { ok, vn_q_vrms, vn_ktc_vrms, snr_jitter_db, vn_total_vrms, "
        "snr_total_db, dominant_noise, jitter_limited, thermal_limited, warnings_list }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "bits": {
                "type": "integer",
                "description": "ADC resolution [bits].",
                "minimum": 1,
                "maximum": 64,
            },
            "v_fs": {
                "type": "number",
                "description": "Full-scale voltage range peak-to-peak [V].",
            },
            "freq_in_hz": {
                "type": "number",
                "description": "Input signal frequency [Hz].",
            },
            "t_jitter_s": {
                "type": "number",
                "description": "Aperture / clock jitter [s RMS].",
            },
            "cap_dac_f": {
                "type": "number",
                "description": "DAC sampling capacitor [F] (default 1 pF).",
            },
            "en_amp_v_per_rtHz": {
                "type": "number",
                "description": "Input-referred amp voltage noise density [V/√Hz] (default 0).",
            },
            "bw_hz": {
                "type": "number",
                "description": "Noise integration bandwidth [Hz] (default 1 MHz).",
            },
            "temp_k": {
                "type": "number",
                "description": "Temperature [K] (default 300 K).",
            },
        },
        "required": ["bits", "v_fs", "freq_in_hz", "t_jitter_s"],
    },
)


@register(_NOISE_BUDGET_SPEC, write=False)
async def adc_total_noise_budget(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = total_noise_budget(
        bits=a.get("bits"),
        v_fs=a.get("v_fs"),
        freq_in_hz=a.get("freq_in_hz"),
        t_jitter_s=a.get("t_jitter_s"),
        cap_dac_f=a.get("cap_dac_f", 1e-12),
        en_amp_v_per_rtHz=a.get("en_amp_v_per_rtHz", 0.0),
        bw_hz=a.get("bw_hz", 1e6),
        temp_k=a.get("temp_k", 300.0),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. adc_oversampling_gain
# ═══════════════════════════════════════════════════════════════════════════════

_OSR_GAIN_SPEC = ToolSpec(
    name="adc_oversampling_gain",
    description=(
        "Compute oversampling and decimation processing gain for an ADC.\n\n"
        "Process gain [dB] = 10×log10(OSR) / 2  (3 dB per octave of oversampling)\n"
        "Optionally compute required OSR for a target ENOB.\n\n"
        "Input: { bits, osr, target_enob? }\n"
        "Returns: { ok, snr_nyquist_db, process_gain_db, snr_with_osr_db, enob_with_osr, "
        "osr_required? }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "bits": {
                "type": "integer",
                "description": "Nyquist-rate ADC resolution [bits].",
                "minimum": 1,
                "maximum": 64,
            },
            "osr": {
                "type": "number",
                "description": "Oversampling ratio (≥ 1).",
            },
            "target_enob": {
                "type": "number",
                "description": "Target ENOB after decimation (optional; triggers OSR requirement calc).",
            },
        },
        "required": ["bits", "osr"],
    },
)


@register(_OSR_GAIN_SPEC, write=False)
async def adc_oversampling_gain(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = oversampling_gain(
        bits=a.get("bits"),
        osr=a.get("osr"),
        target_enob=a.get("target_enob"),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. dac_delta_sigma_sqnr
# ═══════════════════════════════════════════════════════════════════════════════

_DS_SQNR_SPEC = ToolSpec(
    name="dac_delta_sigma_sqnr",
    description=(
        "Compute ideal ΔΣ modulator SQNR and noise-shaping performance.\n\n"
        "Schreier & Temes Eq. 2.10 (Candy & Temes 1992):\n"
        "  SQNR [dB] ≈ 10log10((2L+1)/π^(2L)) + (20L+10)log10(OSR) + 1.76\n\n"
        "Warns if order > 5 (stability) or OSR < 4 (insufficient noise shaping).\n\n"
        "Input: { order, osr }\n"
        "Returns: { ok, order, osr, sqnr_db, enob_equivalent, osr_insufficient }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "order": {
                "type": "integer",
                "description": "Modulator order L (1–8).",
                "minimum": 1,
                "maximum": 8,
            },
            "osr": {
                "type": "number",
                "description": "Oversampling ratio (≥ 2).",
            },
        },
        "required": ["order", "osr"],
    },
)


@register(_DS_SQNR_SPEC, write=False)
async def dac_delta_sigma_sqnr(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = delta_sigma_sqnr(order=a.get("order"), osr=a.get("osr"))
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. adc_sar_conversion_time
# ═══════════════════════════════════════════════════════════════════════════════

_SAR_TIME_SPEC = ToolSpec(
    name="adc_sar_conversion_time",
    description=(
        "SAR ADC conversion time including comparator, switch settling, and RC kickback.\n\n"
        "  t_convert = N × (t_comp + t_sw)\n"
        "  t_settle_rc = (N + 2) × R_src × C_dac\n"
        "  t_total = max(t_convert, t_settle_rc)\n\n"
        "Input: { bits, t_comp_s, t_sw_s, r_src_ohm?, c_dac_f? }\n"
        "Returns: { ok, t_compare_s, t_settle_rc_s, t_total_s, throughput_max_sps }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "bits": {
                "type": "integer",
                "description": "ADC resolution [bits].",
                "minimum": 1,
                "maximum": 64,
            },
            "t_comp_s": {
                "type": "number",
                "description": "Comparator decision time per cycle [s].",
            },
            "t_sw_s": {
                "type": "number",
                "description": "Switch settling time per cycle [s].",
            },
            "r_src_ohm": {
                "type": "number",
                "description": "Source resistance [Ω] (default 0).",
            },
            "c_dac_f": {
                "type": "number",
                "description": "DAC capacitance [F] (default 1 pF).",
            },
        },
        "required": ["bits", "t_comp_s", "t_sw_s"],
    },
)


@register(_SAR_TIME_SPEC, write=False)
async def adc_sar_conversion_time(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = sar_conversion_time(
        bits=a.get("bits"),
        t_comp_s=a.get("t_comp_s"),
        t_sw_s=a.get("t_sw_s"),
        r_src_ohm=a.get("r_src_ohm", 0.0),
        c_dac_f=a.get("c_dac_f", 1e-12),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 9. adc_pipeline_latency
# ═══════════════════════════════════════════════════════════════════════════════

_PIPELINE_SPEC = ToolSpec(
    name="adc_pipeline_latency",
    description=(
        "Pipeline ADC latency, total bit resolution, and stage residue gain.\n\n"
        "  Latency = num_stages × T_clk\n"
        "  total_bits ≈ num_stages × bits_per_stage + flash_bits\n"
        "  stage_gain = 2^bits_per_stage\n\n"
        "Input: { num_stages, bits_per_stage, t_clk_s, flash_bits? }\n"
        "Returns: { ok, total_bits_nominal, latency_s, latency_clocks, stage_gain, throughput_sps }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "num_stages": {
                "type": "integer",
                "description": "Number of pipeline stages.",
                "minimum": 1,
            },
            "bits_per_stage": {
                "type": "integer",
                "description": "Bits resolved per stage (1–8).",
                "minimum": 1,
                "maximum": 8,
            },
            "t_clk_s": {
                "type": "number",
                "description": "Clock period [s].",
            },
            "flash_bits": {
                "type": "integer",
                "description": "Flash backend bits (default 0).",
                "minimum": 0,
            },
        },
        "required": ["num_stages", "bits_per_stage", "t_clk_s"],
    },
)


@register(_PIPELINE_SPEC, write=False)
async def adc_pipeline_latency(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = pipeline_latency(
        num_stages=a.get("num_stages"),
        bits_per_stage=a.get("bits_per_stage"),
        t_clk_s=a.get("t_clk_s"),
        flash_bits=a.get("flash_bits", 0),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 10. dac_glitch_sfdr
# ═══════════════════════════════════════════════════════════════════════════════

_DAC_GLITCH_SPEC = ToolSpec(
    name="dac_glitch_sfdr",
    description=(
        "DAC glitch/settling analysis and SFDR estimate from INL.\n\n"
        "  SFDR [dBc] ≈ −20×log10(INL_lsb × 2^(1−N))\n"
        "  Glitch area = V_glitch × t_glitch  [V·s]\n"
        "  Settling to 0.5 LSB: t_settle = τ × ln(2^N)\n\n"
        "Input: { bits, inl_lsb, v_fs, v_glitch_v, t_glitch_s, tau_s }\n"
        "Returns: { ok, lsb_size_v, sfdr_dbc, e_glitch_vs, t_settle_s }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "bits": {
                "type": "integer",
                "description": "DAC resolution [bits].",
                "minimum": 1,
                "maximum": 64,
            },
            "inl_lsb": {
                "type": "number",
                "description": "Integral nonlinearity [LSBs] (positive).",
            },
            "v_fs": {
                "type": "number",
                "description": "Full-scale voltage range [V].",
            },
            "v_glitch_v": {
                "type": "number",
                "description": "Glitch voltage amplitude [V].",
            },
            "t_glitch_s": {
                "type": "number",
                "description": "Glitch duration [s].",
            },
            "tau_s": {
                "type": "number",
                "description": "Output RC settling time constant [s].",
            },
        },
        "required": ["bits", "inl_lsb", "v_fs", "v_glitch_v", "t_glitch_s", "tau_s"],
    },
)


@register(_DAC_GLITCH_SPEC, write=False)
async def dac_glitch_sfdr_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = dac_glitch_sfdr(
        bits=a.get("bits"),
        inl_lsb=a.get("inl_lsb"),
        v_fs=a.get("v_fs"),
        v_glitch_v=a.get("v_glitch_v"),
        t_glitch_s=a.get("t_glitch_s"),
        tau_s=a.get("tau_s"),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 11. adc_reference_noise
# ═══════════════════════════════════════════════════════════════════════════════

_REF_NOISE_SPEC = ToolSpec(
    name="adc_reference_noise",
    description=(
        "Reference noise and drift contribution to ADC/DAC LSB error.\n\n"
        "  LSB_v = V_ref / 2^N\n"
        "  SNR_ref [dB] = 20×log10(V_ref / (√6 × 2^N × e_ref_rms))\n"
        "  drift_lsb = drift_ppm_per_°C × ΔT × 2^N / 1e6\n\n"
        "Input: { bits, v_ref, e_ref_rms_v, drift_ppm_per_c?, delta_temp_c? }\n"
        "Returns: { ok, lsb_v, snr_ref_db, drift_error_lsb, drift_error_v }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "bits": {
                "type": "integer",
                "description": "Converter resolution [bits].",
                "minimum": 1,
                "maximum": 64,
            },
            "v_ref": {
                "type": "number",
                "description": "Reference voltage [V].",
            },
            "e_ref_rms_v": {
                "type": "number",
                "description": "Integrated reference noise [V RMS].",
            },
            "drift_ppm_per_c": {
                "type": "number",
                "description": "Reference temperature coefficient [ppm/°C] (default 0).",
            },
            "delta_temp_c": {
                "type": "number",
                "description": "Temperature excursion [°C] (default 0).",
            },
        },
        "required": ["bits", "v_ref", "e_ref_rms_v"],
    },
)


@register(_REF_NOISE_SPEC, write=False)
async def adc_reference_noise(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = reference_noise_lsb(
        bits=a.get("bits"),
        v_ref=a.get("v_ref"),
        e_ref_rms_v=a.get("e_ref_rms_v"),
        drift_ppm_per_c=a.get("drift_ppm_per_c", 0.0),
        delta_temp_c=a.get("delta_temp_c", 0.0),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 12. adc_driver_settling
# ═══════════════════════════════════════════════════════════════════════════════

_DRIVER_SETTLING_SPEC = ToolSpec(
    name="adc_driver_settling",
    description=(
        "ADC driver and RC anti-alias filter kickback settling analysis.\n\n"
        "  τ = R × C_in\n"
        "  t_settle = (N + 2) × τ\n"
        "  f_AA_3dB = 1/(2π × R × C_aa)  (if c_aa_f provided)\n"
        "  t_settle_aa = (N+2) × ln(2) / (2π × f_AA)\n\n"
        "Input: { bits, r_ohm, c_in_f, c_aa_f? }\n"
        "Returns: { ok, tau_s, t_settle_s, f_aa_3db_hz, t_settle_aa_s }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "bits": {
                "type": "integer",
                "description": "ADC resolution [bits].",
                "minimum": 1,
                "maximum": 64,
            },
            "r_ohm": {
                "type": "number",
                "description": "Driver source resistance [Ω].",
            },
            "c_in_f": {
                "type": "number",
                "description": "ADC input capacitance [F].",
            },
            "c_aa_f": {
                "type": "number",
                "description": "Anti-alias filter capacitor [F] (optional).",
            },
        },
        "required": ["bits", "r_ohm", "c_in_f"],
    },
)


@register(_DRIVER_SETTLING_SPEC, write=False)
async def adc_driver_settling_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = adc_driver_settling(
        bits=a.get("bits"),
        r_ohm=a.get("r_ohm"),
        c_in_f=a.get("c_in_f"),
        c_aa_f=a.get("c_aa_f"),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 13. adc_bits_for_dynamic_range
# ═══════════════════════════════════════════════════════════════════════════════

_BITS_DR_SPEC = ToolSpec(
    name="adc_bits_for_dynamic_range",
    description=(
        "Minimum ADC bits required to achieve a target dynamic range.\n\n"
        "N_min = ceil((DR_dB − 1.76) / 6.02)\n\n"
        "Input: { dr_db }\n"
        "Returns: { ok, dr_db, bits_min, snr_achieved_db, margin_db }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "dr_db": {
                "type": "number",
                "description": "Target dynamic range [dB].",
            },
        },
        "required": ["dr_db"],
    },
)


@register(_BITS_DR_SPEC, write=False)
async def adc_bits_for_dynamic_range(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = bits_for_dynamic_range(dr_db=a.get("dr_db"))
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# TOOLS export — consumed by plugin._register_tools
# ═══════════════════════════════════════════════════════════════════════════════

TOOLS = [
    (_IDEAL_SNR_SPEC.name,       _IDEAL_SNR_SPEC,       adc_ideal_snr),
    (_SNR_BACKOFF_SPEC.name,     _SNR_BACKOFF_SPEC,     adc_snr_with_backoff),
    (_ENOB_SINAD_SPEC.name,      _ENOB_SINAD_SPEC,      adc_enob_from_sinad),
    (_INTERCONVERT_SPEC.name,    _INTERCONVERT_SPEC,    adc_interconvert_metrics),
    (_NOISE_BUDGET_SPEC.name,    _NOISE_BUDGET_SPEC,    adc_total_noise_budget),
    (_OSR_GAIN_SPEC.name,        _OSR_GAIN_SPEC,        adc_oversampling_gain),
    (_DS_SQNR_SPEC.name,         _DS_SQNR_SPEC,         dac_delta_sigma_sqnr),
    (_SAR_TIME_SPEC.name,        _SAR_TIME_SPEC,        adc_sar_conversion_time),
    (_PIPELINE_SPEC.name,        _PIPELINE_SPEC,        adc_pipeline_latency),
    (_DAC_GLITCH_SPEC.name,      _DAC_GLITCH_SPEC,      dac_glitch_sfdr_tool),
    (_REF_NOISE_SPEC.name,       _REF_NOISE_SPEC,       adc_reference_noise),
    (_DRIVER_SETTLING_SPEC.name, _DRIVER_SETTLING_SPEC, adc_driver_settling_tool),
    (_BITS_DR_SPEC.name,         _BITS_DR_SPEC,         adc_bits_for_dynamic_range),
]
