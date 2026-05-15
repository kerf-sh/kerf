"""
EMC/EMI pre-compliance estimator tools.

Provides five LLM-callable tools:

  emc_radiated_differential  — E-field from a differential-mode current loop
                               (small-loop magnetic dipole, Ott §6.2)
  emc_radiated_common_mode   — E-field from common-mode cable current
                               (long-wire antenna, Ott §6.3)
  emc_emission_margin        — Compare estimated E-field to FCC / CISPR limit lines
                               and return margin in dBμV/m
  emc_near_field_crosstalk   — Capacitive + inductive coupling coefficient between
                               two parallel PCB traces (near-field EMC screening)
  emc_shielding              — Shielding effectiveness of a conductive enclosure
                               (Schelkunoff theory: absorption + reflection + aperture)

All handlers follow the kerf never-raise contract: errors → {"ok": false, "reason": ...}.
Limit exceedances are reported via warnings.warn (never raise).

Author: imranparuk
"""
from __future__ import annotations

import json
from typing import Any

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_electronics.emc.estimate import (
    emission_margin_db,
    near_field_crosstalk,
    radiated_emission_common_mode,
    radiated_emission_differential,
    shielding_effectiveness,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. emc_radiated_differential
# ═══════════════════════════════════════════════════════════════════════════════

_EMC_RAD_DM_SPEC = ToolSpec(
    name="emc_radiated_differential",
    description=(
        "Estimate far-field radiated E-field (dBμV/m) from a differential-mode "
        "current loop on a PCB.\n\n"
        "Model: small-loop (magnetic dipole) far-field approximation from "
        "Ott 'Electromagnetic Compatibility Engineering' (Wiley 2009) §6.2:\n"
        "  E [V/m] = 263e-16 × f² × A × I / r\n\n"
        "Valid in the far field (r > λ/(2π)).  A warning is issued when the "
        "measurement distance is in the near field.\n\n"
        "Input: { freq_hz, loop_area_m2, current_a, distance_m? }\n"
        "Returns: { ok, e_field_vpm, e_field_dbuvm, far_field, ... }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "freq_hz": {
                "type": "number",
                "description": "Frequency [Hz].",
            },
            "loop_area_m2": {
                "type": "number",
                "description": (
                    "Enclosed loop area [m²].  For a PCB trace-return path rectangle "
                    "of dimensions L × W: area = L × W (convert mm² → m² by ÷ 1e6)."
                ),
            },
            "current_a": {
                "type": "number",
                "description": "Loop current amplitude [A] (peak or RMS).",
            },
            "distance_m": {
                "type": "number",
                "description": "Measurement distance [m] (default 3.0 m).",
            },
        },
        "required": ["freq_hz", "loop_area_m2", "current_a"],
    },
)


@register(_EMC_RAD_DM_SPEC, write=False)
async def emc_radiated_differential(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    freq_hz = a.get("freq_hz")
    loop_area_m2 = a.get("loop_area_m2")
    current_a = a.get("current_a")
    distance_m = a.get("distance_m", 3.0)

    result = radiated_emission_differential(
        freq_hz=freq_hz,
        loop_area_m2=loop_area_m2,
        current_a=current_a,
        distance_m=distance_m,
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "unknown error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. emc_radiated_common_mode
# ═══════════════════════════════════════════════════════════════════════════════

_EMC_RAD_CM_SPEC = ToolSpec(
    name="emc_radiated_common_mode",
    description=(
        "Estimate far-field radiated E-field (dBμV/m) from common-mode current "
        "on a cable or PCB trace.\n\n"
        "Model: short-monopole (long-wire) antenna approximation from "
        "Ott §6.3 / Paul 'Introduction to EMC' (2006) §10.5:\n"
        "  E [V/m] = μ₀ × f × I_cm × L / r  (= 1.257e-6 × f × I_cm × L / r)\n\n"
        "Conservative (worst-case) for electrically short cables (L < λ/4).\n"
        "A warning is issued when the cable exceeds λ/4.\n\n"
        "Input: { freq_hz, cable_length_m, current_a, distance_m? }\n"
        "Returns: { ok, e_field_vpm, e_field_dbuvm, electrically_short, ... }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "freq_hz": {
                "type": "number",
                "description": "Frequency [Hz].",
            },
            "cable_length_m": {
                "type": "number",
                "description": "Cable (or trace) length [m].",
            },
            "current_a": {
                "type": "number",
                "description": "Common-mode current amplitude [A].",
            },
            "distance_m": {
                "type": "number",
                "description": "Measurement distance [m] (default 3.0 m).",
            },
        },
        "required": ["freq_hz", "cable_length_m", "current_a"],
    },
)


@register(_EMC_RAD_CM_SPEC, write=False)
async def emc_radiated_common_mode(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    freq_hz = a.get("freq_hz")
    cable_length_m = a.get("cable_length_m")
    current_a = a.get("current_a")
    distance_m = a.get("distance_m", 3.0)

    result = radiated_emission_common_mode(
        freq_hz=freq_hz,
        cable_length_m=cable_length_m,
        current_a=current_a,
        distance_m=distance_m,
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "unknown error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. emc_emission_margin
# ═══════════════════════════════════════════════════════════════════════════════

_EMC_MARGIN_SPEC = ToolSpec(
    name="emc_emission_margin",
    description=(
        "Compare an estimated E-field to FCC Part 15 or CISPR 22/32 radiated "
        "emission limit lines and return the margin in dBμV/m.\n\n"
        "Positive margin = emission is below limit (compliant).  "
        "Negative margin = exceedance; a warning is also issued.\n\n"
        "FCC Part 15 §15.109 limits: Class A at 10 m; Class B at 3 m.\n"
        "CISPR 32:2015 limits: both classes referenced to 10 m.\n"
        "Distance adjustments use 20×log10(d_ref / d) free-space scaling.\n\n"
        "Input: { e_field_dbuvm, freq_hz, standard?, class_?, distance_m? }\n"
        "Returns: { ok, margin_db, passes, limit_dbuvm, ... }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "e_field_dbuvm": {
                "type": "number",
                "description": "Estimated E-field [dBμV/m] at the measurement distance.",
            },
            "freq_hz": {
                "type": "number",
                "description": "Frequency [Hz].",
            },
            "standard": {
                "type": "string",
                "enum": ["fcc", "cispr"],
                "description": "Regulatory standard: 'fcc' or 'cispr' (default 'cispr').",
            },
            "class_": {
                "type": "string",
                "enum": ["A", "B"],
                "description": "Emission class: 'A' (commercial/industrial) or 'B' (residential, default).",
            },
            "distance_m": {
                "type": "number",
                "description": "Measurement distance [m] (default 10.0 m).",
            },
        },
        "required": ["e_field_dbuvm", "freq_hz"],
    },
)


@register(_EMC_MARGIN_SPEC, write=False)
async def emc_emission_margin(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    e_field_dbuvm = a.get("e_field_dbuvm")
    freq_hz = a.get("freq_hz")
    standard = a.get("standard", "cispr")
    class_ = a.get("class_", "B")
    distance_m = a.get("distance_m", 10.0)

    result = emission_margin_db(
        e_field_dbuvm=e_field_dbuvm,
        freq_hz=freq_hz,
        standard=standard,
        class_=class_,
        distance_m=distance_m,
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "unknown error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. emc_near_field_crosstalk
# ═══════════════════════════════════════════════════════════════════════════════

_EMC_CROSSTALK_SPEC = ToolSpec(
    name="emc_near_field_crosstalk",
    description=(
        "Estimate the near-field capacitive + inductive coupling coefficient "
        "between two parallel PCB traces (EMC pre-compliance screening).\n\n"
        "Model: first-order proximity coupling from Paul 'Introduction to EMC' "
        "(2006) §6.3.  Distinct from the SI crosstalk tools which use a "
        "coupled-line model; this tool returns a combined dimensionless coupling "
        "coefficient K_effective suitable for EMC budgeting.\n\n"
        "  Kc ≈ 1 / (1 + (dist/w)²)      — capacitive\n"
        "  Kl ≈ 1 / (1 + (2×dist/h)²)    — inductive\n"
        "  K_combined = sqrt(Kc² + Kl²)\n"
        "  K_effective = K_combined × tanh(L / (100×h))  — length saturation\n\n"
        "Input: { freq_hz, trace_width_mm, trace_spacing_mm, trace_height_mm, "
        "parallel_length_mm, er? }\n"
        "Returns: { ok, Kc, Kl, K_combined, K_effective, ... }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "freq_hz": {
                "type": "number",
                "description": "Frequency [Hz].",
            },
            "trace_width_mm": {
                "type": "number",
                "description": "Trace width [mm].",
            },
            "trace_spacing_mm": {
                "type": "number",
                "description": "Edge-to-edge spacing between the two traces [mm].",
            },
            "trace_height_mm": {
                "type": "number",
                "description": "Trace height above nearest ground plane [mm].",
            },
            "parallel_length_mm": {
                "type": "number",
                "description": "Parallel run length [mm].",
            },
            "er": {
                "type": "number",
                "description": "Substrate relative permittivity (default 4.5 for FR4).",
            },
        },
        "required": [
            "freq_hz",
            "trace_width_mm",
            "trace_spacing_mm",
            "trace_height_mm",
            "parallel_length_mm",
        ],
    },
)


@register(_EMC_CROSSTALK_SPEC, write=False)
async def emc_near_field_crosstalk(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = near_field_crosstalk(
        freq_hz=a.get("freq_hz"),
        trace_width_mm=a.get("trace_width_mm"),
        trace_spacing_mm=a.get("trace_spacing_mm"),
        trace_height_mm=a.get("trace_height_mm"),
        parallel_length_mm=a.get("parallel_length_mm"),
        er=a.get("er", 4.5),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "unknown error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. emc_shielding
# ═══════════════════════════════════════════════════════════════════════════════

_EMC_SHIELD_SPEC = ToolSpec(
    name="emc_shielding",
    description=(
        "Compute shielding effectiveness (SE) of a conductive enclosure.\n\n"
        "Model: Schelkunoff theory (Ott 2009 §5.3-5.4):\n"
        "  SEa [dB] = 131.4 × t × sqrt(f × μr × σr)    — absorption\n"
        "  SEr [dB] = 168 + 10×log10(σr / (μr × f))     — reflection (plane wave)\n"
        "  SE_total = SEa + SEr − SE_multiple\n"
        "  SE_aperture [dB] = 20×log10(c / (2 × f × L_slot))  — slot leakage\n"
        "  SE_effective = min(SE_total, SE_aperture) when aperture present\n\n"
        "Input: { freq_hz, thickness_m, conductivity_relative?, "
        "permeability_relative?, aperture_length_m? }\n"
        "Returns: { ok, se_absorption_db, se_reflection_db, se_total_db, "
        "se_effective_db, aperture_limited, ... }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "freq_hz": {
                "type": "number",
                "description": "Frequency [Hz].",
            },
            "thickness_m": {
                "type": "number",
                "description": "Enclosure wall thickness [m].",
            },
            "conductivity_relative": {
                "type": "number",
                "description": (
                    "Relative conductivity σr (copper = 1.0, aluminium ≈ 0.61, "
                    "steel ≈ 0.10).  Default 1.0."
                ),
            },
            "permeability_relative": {
                "type": "number",
                "description": (
                    "Relative permeability μr (copper/aluminium = 1.0, steel ≈ 1000).  "
                    "Default 1.0."
                ),
            },
            "aperture_length_m": {
                "type": "number",
                "description": (
                    "Longest dimension of the largest aperture/slot [m].  "
                    "Set to 0 or omit for a sealed enclosure (default 0)."
                ),
            },
        },
        "required": ["freq_hz", "thickness_m"],
    },
)


@register(_EMC_SHIELD_SPEC, write=False)
async def emc_shielding(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = shielding_effectiveness(
        freq_hz=a.get("freq_hz"),
        thickness_m=a.get("thickness_m"),
        conductivity_relative=a.get("conductivity_relative", 1.0),
        permeability_relative=a.get("permeability_relative", 1.0),
        aperture_length_m=a.get("aperture_length_m", 0.0),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "unknown error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# TOOLS export — consumed by plugin._register_tools
# ═══════════════════════════════════════════════════════════════════════════════

TOOLS = [
    (_EMC_RAD_DM_SPEC.name,    _EMC_RAD_DM_SPEC,    emc_radiated_differential),
    (_EMC_RAD_CM_SPEC.name,    _EMC_RAD_CM_SPEC,    emc_radiated_common_mode),
    (_EMC_MARGIN_SPEC.name,    _EMC_MARGIN_SPEC,    emc_emission_margin),
    (_EMC_CROSSTALK_SPEC.name, _EMC_CROSSTALK_SPEC, emc_near_field_crosstalk),
    (_EMC_SHIELD_SPEC.name,    _EMC_SHIELD_SPEC,    emc_shielding),
]
