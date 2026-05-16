"""
RF & fiber-optic link budget — LLM tools.

Provides LLM-callable tools:

  linkbudget_fspl             — free-space path loss (Friis)
  linkbudget_eirp             — effective isotropic radiated power
  linkbudget_received_power   — Friis received power
  linkbudget_noise_cascade    — cascaded noise figure (Friis noise formula)
  linkbudget_thermal_noise    — thermal noise floor kTB
  linkbudget_cn               — carrier-to-noise ratio
  linkbudget_shannon          — Shannon capacity & spectral efficiency
  linkbudget_ber_bpsk         — BER for BPSK at given Eb/N0
  linkbudget_ber_qam          — BER for M-QAM at given Eb/N0
  linkbudget_required_ebn0    — required Eb/N0 for target BER and modulation
  linkbudget_rain_atten       — rain attenuation (ITU-R P.838-3)
  linkbudget_rf_budget        — complete RF link budget with margin verdict
  linkbudget_fiber_budget     — fiber optical power budget
  linkbudget_fiber_cd         — chromatic dispersion bandwidth limit
  linkbudget_fiber_osnr       — optical SNR for amplified fiber link

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

from kerf_electronics.linkbudget.link import (
    fspl_db,
    eirp_dbw,
    received_power_dbw,
    noise_figure_cascade,
    thermal_noise_floor_dbw,
    cn_ratio_db,
    eb_n0_db,
    shannon_capacity,
    spectral_efficiency,
    ber_bpsk,
    ber_qpsk,
    ber_qam,
    ber_psk,
    required_eb_n0_bpsk,
    required_eb_n0_qpsk,
    required_eb_n0_qam,
    required_eb_n0_psk,
    rain_attenuation_db,
    atmospheric_attenuation_db,
    rf_link_budget,
    fiber_power_budget,
    chromatic_dispersion_bandwidth,
    modal_dispersion_bandwidth,
    fiber_osnr,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. linkbudget_fspl
# ═══════════════════════════════════════════════════════════════════════════════

_FSPL_SPEC = ToolSpec(
    name="linkbudget_fspl",
    description=(
        "Compute free-space path loss (FSPL) using the Friis (1946) formula.\n\n"
        "FSPL [dB] = 20×log10(4π×d×f/c)\n\n"
        "Input: { freq_hz, distance_m }\n"
        "Returns: { ok, fspl_db, wavelength_m }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "freq_hz": {"type": "number", "description": "Carrier frequency [Hz]."},
            "distance_m": {"type": "number", "description": "Link distance [m]."},
        },
        "required": ["freq_hz", "distance_m"],
    },
)


@register(_FSPL_SPEC, write=False)
async def linkbudget_fspl(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = fspl_db(freq_hz=a.get("freq_hz"), distance_m=a.get("distance_m"))
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. linkbudget_eirp
# ═══════════════════════════════════════════════════════════════════════════════

_EIRP_SPEC = ToolSpec(
    name="linkbudget_eirp",
    description=(
        "Compute Effective Isotropic Radiated Power (EIRP).\n\n"
        "EIRP [dBW] = P_tx [dBW] + G_tx [dBi]\n\n"
        "Input: { p_tx_dbw, g_tx_dbi }\n"
        "Returns: { ok, eirp_dbw, eirp_dbm }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "p_tx_dbw": {"type": "number", "description": "Transmitter output power [dBW]."},
            "g_tx_dbi": {"type": "number", "description": "Transmit antenna gain [dBi]."},
        },
        "required": ["p_tx_dbw", "g_tx_dbi"],
    },
)


@register(_EIRP_SPEC, write=False)
async def linkbudget_eirp(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = eirp_dbw(p_tx_dbw=a.get("p_tx_dbw"), g_tx_dbi=a.get("g_tx_dbi"))
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. linkbudget_received_power
# ═══════════════════════════════════════════════════════════════════════════════

_RX_POWER_SPEC = ToolSpec(
    name="linkbudget_received_power",
    description=(
        "Compute received signal power using the Friis transmission equation.\n\n"
        "P_rx [dBW] = P_tx + G_tx − FSPL + G_rx − L_other\n\n"
        "Input: { p_tx_dbw, g_tx_dbi, g_rx_dbi, freq_hz, distance_m, other_losses_db? }\n"
        "Returns: { ok, p_rx_dbw, p_rx_dbm, fspl_db, eirp_dbw, link_loss_db }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "p_tx_dbw": {"type": "number", "description": "Transmit power [dBW]."},
            "g_tx_dbi": {"type": "number", "description": "Transmit antenna gain [dBi]."},
            "g_rx_dbi": {"type": "number", "description": "Receive antenna gain [dBi]."},
            "freq_hz": {"type": "number", "description": "Carrier frequency [Hz]."},
            "distance_m": {"type": "number", "description": "Link distance [m]."},
            "other_losses_db": {
                "type": "number",
                "description": "Miscellaneous losses (rain, cable, pointing) [dB] (default 0).",
            },
        },
        "required": ["p_tx_dbw", "g_tx_dbi", "g_rx_dbi", "freq_hz", "distance_m"],
    },
)


@register(_RX_POWER_SPEC, write=False)
async def linkbudget_received_power(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = received_power_dbw(
        p_tx_dbw=a.get("p_tx_dbw"),
        g_tx_dbi=a.get("g_tx_dbi"),
        g_rx_dbi=a.get("g_rx_dbi"),
        freq_hz=a.get("freq_hz"),
        distance_m=a.get("distance_m"),
        other_losses_db=a.get("other_losses_db", 0.0),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. linkbudget_noise_cascade
# ═══════════════════════════════════════════════════════════════════════════════

_NF_CASCADE_SPEC = ToolSpec(
    name="linkbudget_noise_cascade",
    description=(
        "Compute cascaded noise figure for a receiver chain using Friis' noise formula.\n\n"
        "F_total = F1 + (F2−1)/G1 + (F3−1)/(G1×G2) + …\n\n"
        "Input: { nf_db_list: [...], gain_db_list: [...] }\n"
        "Returns: { ok, nf_cascade_db, f_cascade_linear, stage_count }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "nf_db_list": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Noise figures of each stage [dB], in order from input to output.",
            },
            "gain_db_list": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Gains of each stage [dB], same order as nf_db_list.",
            },
        },
        "required": ["nf_db_list", "gain_db_list"],
    },
)


@register(_NF_CASCADE_SPEC, write=False)
async def linkbudget_noise_cascade(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = noise_figure_cascade(
        nf_db_list=a.get("nf_db_list"),
        gain_db_list=a.get("gain_db_list"),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. linkbudget_thermal_noise
# ═══════════════════════════════════════════════════════════════════════════════

_THERMAL_SPEC = ToolSpec(
    name="linkbudget_thermal_noise",
    description=(
        "Compute thermal noise floor N = kTB.\n\n"
        "N [dBW] = 10×log10(k × T × B)\n"
        "where k = 1.38065e-23 J/K, T in Kelvin, B in Hz.\n\n"
        "Input: { bandwidth_hz, temp_k? }\n"
        "Returns: { ok, noise_dbw, noise_dbm, noise_w }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "bandwidth_hz": {"type": "number", "description": "Noise bandwidth [Hz]."},
            "temp_k": {"type": "number", "description": "Temperature [K] (default 290 K)."},
        },
        "required": ["bandwidth_hz"],
    },
)


@register(_THERMAL_SPEC, write=False)
async def linkbudget_thermal_noise(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = thermal_noise_floor_dbw(
        bandwidth_hz=a.get("bandwidth_hz"),
        temp_k=a.get("temp_k", 290.0),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. linkbudget_cn
# ═══════════════════════════════════════════════════════════════════════════════

_CN_SPEC = ToolSpec(
    name="linkbudget_cn",
    description=(
        "Compute carrier-to-noise ratio C/N.\n\n"
        "C/N [dB] = P_rx [dBW] − N [dBW]\n\n"
        "Input: { p_rx_dbw, noise_dbw }\n"
        "Returns: { ok, cn_db }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "p_rx_dbw": {"type": "number", "description": "Received carrier power [dBW]."},
            "noise_dbw": {"type": "number", "description": "Noise power [dBW]."},
        },
        "required": ["p_rx_dbw", "noise_dbw"],
    },
)


@register(_CN_SPEC, write=False)
async def linkbudget_cn(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = cn_ratio_db(p_rx_dbw=a.get("p_rx_dbw"), noise_dbw=a.get("noise_dbw"))
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. linkbudget_shannon
# ═══════════════════════════════════════════════════════════════════════════════

_SHANNON_SPEC = ToolSpec(
    name="linkbudget_shannon",
    description=(
        "Compute Shannon channel capacity and spectral efficiency.\n\n"
        "C [bps] = B × log2(1 + SNR_linear)\n"
        "η [bps/Hz] = log2(1 + SNR_linear)\n\n"
        "Input: { bandwidth_hz, snr_db }\n"
        "Returns: { ok, capacity_bps, spectral_efficiency_bps_per_hz }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "bandwidth_hz": {"type": "number", "description": "Channel bandwidth [Hz]."},
            "snr_db": {"type": "number", "description": "Signal-to-noise ratio [dB]."},
        },
        "required": ["bandwidth_hz", "snr_db"],
    },
)


@register(_SHANNON_SPEC, write=False)
async def linkbudget_shannon(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = shannon_capacity(
        bandwidth_hz=a.get("bandwidth_hz"),
        snr_db=a.get("snr_db"),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. linkbudget_ber_bpsk
# ═══════════════════════════════════════════════════════════════════════════════

_BER_BPSK_SPEC = ToolSpec(
    name="linkbudget_ber_bpsk",
    description=(
        "Compute BER for coherent BPSK (or QPSK per bit) at a given Eb/N0.\n\n"
        "BPSK: BER = Q(sqrt(2 × Eb/N0)) = 0.5 × erfc(sqrt(Eb/N0))\n"
        "QPSK: same BER as BPSK on a per-bit basis.\n\n"
        "Input: { eb_n0_db, modulation? }\n"
        "Returns: { ok, ber, eb_n0_db, modulation }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "eb_n0_db": {"type": "number", "description": "Eb/N0 [dB]."},
            "modulation": {
                "type": "string",
                "enum": ["BPSK", "QPSK"],
                "description": "Modulation scheme (default 'BPSK').",
            },
        },
        "required": ["eb_n0_db"],
    },
)


@register(_BER_BPSK_SPEC, write=False)
async def linkbudget_ber_bpsk(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    eb_n0 = a.get("eb_n0_db")
    if not isinstance(eb_n0, (int, float)):
        return err_payload("eb_n0_db must be a number", "BAD_ARGS")

    modulation = a.get("modulation", "BPSK").upper()
    import math as _math
    eb_n0_linear = 10.0 ** (eb_n0 / 10.0)
    ber_val = ber_bpsk(eb_n0_linear)
    return ok_payload({"ok": True, "ber": ber_val, "eb_n0_db": eb_n0, "modulation": modulation})


# ═══════════════════════════════════════════════════════════════════════════════
# 9. linkbudget_ber_qam
# ═══════════════════════════════════════════════════════════════════════════════

_BER_QAM_SPEC = ToolSpec(
    name="linkbudget_ber_qam",
    description=(
        "Compute approximate BER for Gray-coded M-QAM at a given Eb/N0.\n\n"
        "BER ≈ (4/log2(M)) × (1−1/sqrt(M)) × Q(sqrt(6×log2(M)×Eb/N0/(M−1)))\n\n"
        "Input: { eb_n0_db, m }\n"
        "Returns: { ok, ber, eb_n0_db, m }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "eb_n0_db": {"type": "number", "description": "Eb/N0 [dB]."},
            "m": {
                "type": "integer",
                "description": "QAM order M (must be a power of 2, >= 4: 4, 16, 64, 256).",
            },
        },
        "required": ["eb_n0_db", "m"],
    },
)


@register(_BER_QAM_SPEC, write=False)
async def linkbudget_ber_qam(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    eb_n0 = a.get("eb_n0_db")
    m = a.get("m")
    if not isinstance(eb_n0, (int, float)):
        return err_payload("eb_n0_db must be a number", "BAD_ARGS")
    if not isinstance(m, int) or m < 4 or (m & (m - 1)) != 0:
        return err_payload("m must be an integer power of 2 and >= 4", "BAD_ARGS")

    eb_n0_linear = 10.0 ** (eb_n0 / 10.0)
    try:
        ber_val = ber_qam(eb_n0_linear, m)
    except ValueError as exc:
        return err_payload(str(exc), "BAD_ARGS")

    return ok_payload({"ok": True, "ber": ber_val, "eb_n0_db": eb_n0, "m": m})


# ═══════════════════════════════════════════════════════════════════════════════
# 10. linkbudget_required_ebn0
# ═══════════════════════════════════════════════════════════════════════════════

_REQ_EBN0_SPEC = ToolSpec(
    name="linkbudget_required_ebn0",
    description=(
        "Find the required Eb/N0 [dB] for a target BER and modulation scheme.\n\n"
        "Supported modulations: BPSK, QPSK, M-QAM (m=4,16,64,256), M-PSK (m=2,4,8,16,32).\n"
        "Uses bisection inversion of the BER formulas.\n\n"
        "Input: { target_ber, modulation, m? }\n"
        "Returns: { ok, eb_n0_db, eb_n0_linear, target_ber, modulation }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "target_ber": {"type": "number", "description": "Target bit error rate (e.g. 1e-6)."},
            "modulation": {
                "type": "string",
                "enum": ["BPSK", "QPSK", "QAM", "PSK"],
                "description": "Modulation type.",
            },
            "m": {
                "type": "integer",
                "description": "Modulation order for QAM/PSK (e.g. m=64 for 64-QAM, m=8 for 8-PSK).",
            },
        },
        "required": ["target_ber", "modulation"],
    },
)


@register(_REQ_EBN0_SPEC, write=False)
async def linkbudget_required_ebn0(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    target_ber = a.get("target_ber")
    modulation = str(a.get("modulation", "BPSK")).upper()
    m = a.get("m")

    if modulation == "BPSK":
        result = required_eb_n0_bpsk(target_ber)
    elif modulation == "QPSK":
        result = required_eb_n0_qpsk(target_ber)
    elif modulation == "QAM":
        if not isinstance(m, int):
            return err_payload("m (integer) required for QAM", "BAD_ARGS")
        result = required_eb_n0_qam(target_ber, m)
    elif modulation == "PSK":
        if not isinstance(m, int):
            return err_payload("m (integer) required for PSK", "BAD_ARGS")
        result = required_eb_n0_psk(target_ber, m)
    else:
        return err_payload(f"unsupported modulation: {modulation}", "BAD_ARGS")

    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 11. linkbudget_rain_atten
# ═══════════════════════════════════════════════════════════════════════════════

_RAIN_SPEC = ToolSpec(
    name="linkbudget_rain_atten",
    description=(
        "Rain path attenuation using ITU-R P.838-3 specific attenuation model.\n\n"
        "γ_R [dB/km] = k × R^α\n"
        "A_rain [dB] = γ_R × L\n\n"
        "Input: { freq_hz, rain_rate_mm_per_hr, path_length_km }\n"
        "Returns: { ok, a_rain_db, specific_atten_db_per_km }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "freq_hz": {"type": "number", "description": "Carrier frequency [Hz]."},
            "rain_rate_mm_per_hr": {
                "type": "number",
                "description": "Rain rate [mm/h] (25 = moderate, 50 = heavy, 100 = tropical).",
            },
            "path_length_km": {"type": "number", "description": "Path length through rain [km]."},
        },
        "required": ["freq_hz", "rain_rate_mm_per_hr", "path_length_km"],
    },
)


@register(_RAIN_SPEC, write=False)
async def linkbudget_rain_atten(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = rain_attenuation_db(
        freq_hz=a.get("freq_hz"),
        rain_rate_mm_per_hr=a.get("rain_rate_mm_per_hr"),
        path_length_km=a.get("path_length_km"),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 12. linkbudget_rf_budget
# ═══════════════════════════════════════════════════════════════════════════════

_RF_BUDGET_SPEC = ToolSpec(
    name="linkbudget_rf_budget",
    description=(
        "Complete RF link budget: FSPL, EIRP, received power, thermal noise, "
        "C/N, and a margin verdict.\n\n"
        "Input: { p_tx_dbw, g_tx_dbi, g_rx_dbi, freq_hz, distance_m, "
        "noise_figure_db, bandwidth_hz, required_snr_db, other_losses_db?, t_ant_k? }\n"
        "Returns: { ok, passes, margin_db, p_rx_dbw, fspl_db, cn_db, t_sys_k, ... }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "p_tx_dbw": {"type": "number", "description": "Transmit power [dBW]."},
            "g_tx_dbi": {"type": "number", "description": "Transmit antenna gain [dBi]."},
            "g_rx_dbi": {"type": "number", "description": "Receive antenna gain [dBi]."},
            "freq_hz": {"type": "number", "description": "Carrier frequency [Hz]."},
            "distance_m": {"type": "number", "description": "Link distance [m]."},
            "noise_figure_db": {"type": "number", "description": "Receiver noise figure [dB]."},
            "bandwidth_hz": {"type": "number", "description": "Noise/signal bandwidth [Hz]."},
            "required_snr_db": {"type": "number", "description": "Required SNR at receiver [dB]."},
            "other_losses_db": {
                "type": "number",
                "description": "Additional losses (rain, cable, pointing) [dB] (default 0).",
            },
            "t_ant_k": {
                "type": "number",
                "description": "Antenna noise temperature [K] (default 0).",
            },
        },
        "required": [
            "p_tx_dbw", "g_tx_dbi", "g_rx_dbi", "freq_hz", "distance_m",
            "noise_figure_db", "bandwidth_hz", "required_snr_db",
        ],
    },
)


@register(_RF_BUDGET_SPEC, write=False)
async def linkbudget_rf_budget(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = rf_link_budget(
        p_tx_dbw=a.get("p_tx_dbw"),
        g_tx_dbi=a.get("g_tx_dbi"),
        g_rx_dbi=a.get("g_rx_dbi"),
        freq_hz=a.get("freq_hz"),
        distance_m=a.get("distance_m"),
        noise_figure_db=a.get("noise_figure_db"),
        bandwidth_hz=a.get("bandwidth_hz"),
        required_snr_db=a.get("required_snr_db"),
        other_losses_db=a.get("other_losses_db", 0.0),
        t_ant_k=a.get("t_ant_k", 0.0),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 13. linkbudget_fiber_budget
# ═══════════════════════════════════════════════════════════════════════════════

_FIBER_BUDGET_SPEC = ToolSpec(
    name="linkbudget_fiber_budget",
    description=(
        "Fiber-optic link power budget.\n\n"
        "Margin [dB] = (P_tx − Rx_sensitivity) − (fiber_loss + connectors + splices + safety)\n\n"
        "Positive margin → link OK; negative → insufficient power (warning issued).\n\n"
        "Input: { p_tx_dbm, rx_sensitivity_dbm, fiber_loss_db_per_km, length_km, "
        "connector_loss_db?, splice_loss_db?, safety_margin_db? }\n"
        "Returns: { ok, passes, margin_db, available_loss_db, system_penalty_db }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "p_tx_dbm": {"type": "number", "description": "Transmitter output power [dBm]."},
            "rx_sensitivity_dbm": {
                "type": "number",
                "description": "Receiver minimum sensitivity [dBm].",
            },
            "fiber_loss_db_per_km": {
                "type": "number",
                "description": "Fiber attenuation [dB/km] (SMF-28 @ 1310 nm ≈ 0.35, @ 1550 nm ≈ 0.20).",
            },
            "length_km": {"type": "number", "description": "Fiber span length [km]."},
            "connector_loss_db": {
                "type": "number",
                "description": "Total connector insertion loss [dB] (default 0).",
            },
            "splice_loss_db": {
                "type": "number",
                "description": "Total splice loss [dB] (default 0).",
            },
            "safety_margin_db": {
                "type": "number",
                "description": "Engineering safety margin [dB] (default 3.0).",
            },
        },
        "required": ["p_tx_dbm", "rx_sensitivity_dbm", "fiber_loss_db_per_km", "length_km"],
    },
)


@register(_FIBER_BUDGET_SPEC, write=False)
async def linkbudget_fiber_budget(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = fiber_power_budget(
        p_tx_dbm=a.get("p_tx_dbm"),
        rx_sensitivity_dbm=a.get("rx_sensitivity_dbm"),
        fiber_loss_db_per_km=a.get("fiber_loss_db_per_km"),
        length_km=a.get("length_km"),
        connector_loss_db=a.get("connector_loss_db", 0.0),
        splice_loss_db=a.get("splice_loss_db", 0.0),
        safety_margin_db=a.get("safety_margin_db", 3.0),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 14. linkbudget_fiber_cd
# ═══════════════════════════════════════════════════════════════════════════════

_FIBER_CD_SPEC = ToolSpec(
    name="linkbudget_fiber_cd",
    description=(
        "Chromatic dispersion bandwidth limit for single-mode fiber.\n\n"
        "CD_total [ps] = D × L [km] × Δλ [nm]\n"
        "BW_limit [bps] ≈ 1 / (4 × CD_total_s)   (NRZ 0.25/T rule)\n\n"
        "Input: { dispersion_ps_per_nm_km, length_km, source_linewidth_nm, bit_rate_bps? }\n"
        "Returns: { ok, cd_total_ps, bw_limit_bps, dispersion_limited? }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "dispersion_ps_per_nm_km": {
                "type": "number",
                "description": "Chromatic dispersion coefficient D [ps/(nm·km)] "
                               "(SMF-28 @ 1550 nm ≈ 17 ps/nm/km).",
            },
            "length_km": {"type": "number", "description": "Fiber span length [km]."},
            "source_linewidth_nm": {
                "type": "number",
                "description": "Source spectral linewidth [nm] (DFB laser ≈ 0.1 nm).",
            },
            "bit_rate_bps": {
                "type": "number",
                "description": "Signal bit rate [bps] — if provided, returns dispersion_limited flag.",
            },
        },
        "required": ["dispersion_ps_per_nm_km", "length_km", "source_linewidth_nm"],
    },
)


@register(_FIBER_CD_SPEC, write=False)
async def linkbudget_fiber_cd(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = chromatic_dispersion_bandwidth(
        dispersion_ps_per_nm_km=a.get("dispersion_ps_per_nm_km"),
        length_km=a.get("length_km"),
        source_linewidth_nm=a.get("source_linewidth_nm"),
        bit_rate_bps=a.get("bit_rate_bps"),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 15. linkbudget_fiber_osnr
# ═══════════════════════════════════════════════════════════════════════════════

_FIBER_OSNR_SPEC = ToolSpec(
    name="linkbudget_fiber_osnr",
    description=(
        "Optical SNR (OSNR) for a multi-span EDFA-amplified fiber link.\n\n"
        "OSNR [dB] = P_signal − n_spans × (NF/2 × h × f × B_o)\n\n"
        "Input: { p_signal_dbm, nf_amp_db, freq_hz, n_spans, noise_bandwidth_hz? }\n"
        "Returns: { ok, osnr_db, n_ase_dbm, n_spans, ... }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "p_signal_dbm": {
                "type": "number",
                "description": "Signal power per channel [dBm].",
            },
            "nf_amp_db": {
                "type": "number",
                "description": "Amplifier noise figure [dB] (typical EDFA: 4–6 dB).",
            },
            "freq_hz": {
                "type": "number",
                "description": "Optical carrier frequency [Hz] "
                               "(e.g. 193.1e12 for 1550 nm C-band).",
            },
            "n_spans": {
                "type": "integer",
                "description": "Number of amplified spans.",
            },
            "noise_bandwidth_hz": {
                "type": "number",
                "description": "Optical noise bandwidth [Hz] "
                               "(default 12.5 GHz = 0.1 nm @ 1550 nm).",
            },
        },
        "required": ["p_signal_dbm", "nf_amp_db", "freq_hz", "n_spans"],
    },
)


@register(_FIBER_OSNR_SPEC, write=False)
async def linkbudget_fiber_osnr(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = fiber_osnr(
        p_signal_dbm=a.get("p_signal_dbm"),
        nf_amp_db=a.get("nf_amp_db"),
        freq_hz=a.get("freq_hz"),
        n_spans=a.get("n_spans"),
        noise_bandwidth_hz=a.get("noise_bandwidth_hz", 12.5e9),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# TOOLS export — consumed by plugin._register_tools
# ═══════════════════════════════════════════════════════════════════════════════

TOOLS = [
    (_FSPL_SPEC.name,         _FSPL_SPEC,         linkbudget_fspl),
    (_EIRP_SPEC.name,         _EIRP_SPEC,         linkbudget_eirp),
    (_RX_POWER_SPEC.name,     _RX_POWER_SPEC,     linkbudget_received_power),
    (_NF_CASCADE_SPEC.name,   _NF_CASCADE_SPEC,   linkbudget_noise_cascade),
    (_THERMAL_SPEC.name,      _THERMAL_SPEC,      linkbudget_thermal_noise),
    (_CN_SPEC.name,           _CN_SPEC,           linkbudget_cn),
    (_SHANNON_SPEC.name,      _SHANNON_SPEC,      linkbudget_shannon),
    (_BER_BPSK_SPEC.name,     _BER_BPSK_SPEC,     linkbudget_ber_bpsk),
    (_BER_QAM_SPEC.name,      _BER_QAM_SPEC,      linkbudget_ber_qam),
    (_REQ_EBN0_SPEC.name,     _REQ_EBN0_SPEC,     linkbudget_required_ebn0),
    (_RAIN_SPEC.name,         _RAIN_SPEC,         linkbudget_rain_atten),
    (_RF_BUDGET_SPEC.name,    _RF_BUDGET_SPEC,    linkbudget_rf_budget),
    (_FIBER_BUDGET_SPEC.name, _FIBER_BUDGET_SPEC, linkbudget_fiber_budget),
    (_FIBER_CD_SPEC.name,     _FIBER_CD_SPEC,     linkbudget_fiber_cd),
    (_FIBER_OSNR_SPEC.name,   _FIBER_OSNR_SPEC,   linkbudget_fiber_osnr),
]
