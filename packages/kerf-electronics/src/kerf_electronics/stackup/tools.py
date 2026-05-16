"""
PCB controlled-impedance stackup designer — LLM tools.

Provides LLM-callable tools:

  stackup_copper_weight          — copper-weight oz/ft² → thickness µm / mm
  stackup_microstrip_z0          — single-ended microstrip Z0 (Hammerstad-Jensen)
  stackup_embedded_microstrip_z0 — embedded (covered) microstrip Z0
  stackup_stripline_z0_symmetric — symmetric stripline Z0 (IPC-2141A eq. 2-1)
  stackup_stripline_z0_asymmetric — asymmetric stripline Z0 (Wadell §4.5)
  stackup_cpwg_z0                — coplanar-waveguide-with-ground Z0
  stackup_diff_microstrip_z0     — differential microstrip Zdiff (Wadell §3.7)
  stackup_diff_stripline_z0      — differential stripline Zdiff (Wadell §4.3)
  stackup_effective_er           — effective dielectric constant
  stackup_propagation_delay      — propagation delay ps/mm from er_eff
  stackup_wavelength             — guided wavelength on a transmission line
  stackup_trace_width_solver     — bisection solver: trace width for target Z0
  stackup_diff_spacing_solver    — bisection solver: spacing for target Zdiff
  stackup_conductor_loss         — skin-effect attenuation dB/mm vs frequency
  stackup_dielectric_loss        — loss-tangent attenuation dB/mm vs frequency
  stackup_thickness              — total PCB thickness from layer list
  stackup_impedance_budget       — Z0 across all controlled-impedance nets

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

from kerf_electronics.stackup.impedance import (
    copper_weight_to_thickness_mm,
    microstrip_z0,
    embedded_microstrip_z0,
    stripline_z0_symmetric,
    stripline_z0_asymmetric,
    cpwg_z0,
    differential_microstrip_z0,
    differential_stripline_z0,
    effective_er,
    propagation_delay_ps_per_mm,
    wavelength_mm,
    trace_width_for_z0,
    diff_pair_spacing_for_zdiff,
    conductor_loss_db_per_mm,
    dielectric_loss_db_per_mm,
    stackup_thickness_mm,
    stackup_impedance_budget,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. stackup_copper_weight
# ═══════════════════════════════════════════════════════════════════════════════

_COPPER_WEIGHT_SPEC = ToolSpec(
    name="stackup_copper_weight",
    description=(
        "Convert PCB copper weight [oz/ft²] to foil thickness [µm and mm].\n\n"
        "Industry standard (IPC-6012 §3.2): 1 oz/ft² = 34.8 µm.\n\n"
        "Common copper weights: 0.5 oz (17.5 µm), 1 oz (35 µm), 2 oz (70 µm).\n\n"
        "Input: { oz }\n"
        "Returns: { ok, oz, thickness_mm, thickness_um }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "oz": {
                "type": "number",
                "description": "Copper weight [oz/ft²], e.g. 0.5, 1.0, 2.0.",
            },
        },
        "required": ["oz"],
    },
)


@register(_COPPER_WEIGHT_SPEC, write=False)
async def stackup_copper_weight(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = copper_weight_to_thickness_mm(oz=a.get("oz"))
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. stackup_microstrip_z0
# ═══════════════════════════════════════════════════════════════════════════════

_MICROSTRIP_Z0_SPEC = ToolSpec(
    name="stackup_microstrip_z0",
    description=(
        "Compute single-ended microstrip characteristic impedance Z0 [Ω].\n\n"
        "Model: Hammerstad-Jensen closed-form with trace-thickness correction "
        "(Wadell §3.4 / IPC-2141A eq. 1-1/1-2).\n\n"
        "Typical 50 Ω microstrip on FR-4 (er=4.3, H=0.2 mm): W ≈ 0.44 mm.\n\n"
        "Fab-range warnings issued for W < 0.075 mm or H < 0.05 mm.\n\n"
        "Input: { W_mm, H_mm, er, T_mm? }\n"
        "Returns: { ok, Z0, er_eff, W_mm, H_mm, er, T_mm, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "W_mm": {
                "type": "number",
                "description": "Trace width [mm].",
            },
            "H_mm": {
                "type": "number",
                "description": "Dielectric height above reference plane [mm].",
            },
            "er": {
                "type": "number",
                "description": "Substrate relative permittivity (e.g. 4.3 for FR-4).",
            },
            "T_mm": {
                "type": "number",
                "description": "Trace thickness [mm] (default 0.035 mm = 1 oz copper).",
            },
        },
        "required": ["W_mm", "H_mm", "er"],
    },
)


@register(_MICROSTRIP_Z0_SPEC, write=False)
async def stackup_microstrip_z0(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = microstrip_z0(
        W_mm=a.get("W_mm"),
        H_mm=a.get("H_mm"),
        er=a.get("er"),
        T_mm=a.get("T_mm", 0.035),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. stackup_embedded_microstrip_z0
# ═══════════════════════════════════════════════════════════════════════════════

_EMB_MICROSTRIP_SPEC = ToolSpec(
    name="stackup_embedded_microstrip_z0",
    description=(
        "Compute embedded microstrip Z0 [Ω] (trace with a dielectric cover layer).\n\n"
        "The cover layer increases er_eff vs. open microstrip, lowering Z0.\n"
        "Model: Wadell §3.4.4: er_eff_emb = er_eff * (1 - exp(-1.55 * d / H)).\n"
        "For d=0 this equals standard microstrip.\n\n"
        "Input: { W_mm, H_mm, er, d_mm, T_mm? }\n"
        "Returns: { ok, Z0, er_eff, er_eff_embedded, W_mm, H_mm, er, d_mm, T_mm }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "W_mm": {"type": "number", "description": "Trace width [mm]."},
            "H_mm": {"type": "number", "description": "Dielectric height above reference plane [mm]."},
            "er": {"type": "number", "description": "Substrate relative permittivity."},
            "d_mm": {
                "type": "number",
                "description": "Cover layer thickness above the trace [mm] (0 = open microstrip).",
            },
            "T_mm": {"type": "number", "description": "Trace thickness [mm] (default 0.035 mm)."},
        },
        "required": ["W_mm", "H_mm", "er", "d_mm"],
    },
)


@register(_EMB_MICROSTRIP_SPEC, write=False)
async def stackup_embedded_microstrip_z0(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = embedded_microstrip_z0(
        W_mm=a.get("W_mm"),
        H_mm=a.get("H_mm"),
        er=a.get("er"),
        d_mm=a.get("d_mm"),
        T_mm=a.get("T_mm", 0.035),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. stackup_stripline_z0_symmetric
# ═══════════════════════════════════════════════════════════════════════════════

_STRIPLINE_SYM_SPEC = ToolSpec(
    name="stackup_stripline_z0_symmetric",
    description=(
        "Compute symmetric stripline Z0 [Ω] (trace centred between two ground planes).\n\n"
        "Model: IPC-2141A eq. 2-1 / Wadell §4.3.\n"
        "Formula: Z0 = (60/√er) × ln(4B / (0.67π(0.8W + T)))\n"
        "where B = total dielectric thickness between reference planes.\n\n"
        "Typical 50 Ω stripline on FR-4 (er=4.3, B=0.4 mm, T=0.035 mm): W ≈ 0.20 mm.\n\n"
        "Input: { W_mm, B_mm, er, T_mm? }\n"
        "Returns: { ok, Z0, er_eff, W_mm, B_mm, er, T_mm }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "W_mm": {"type": "number", "description": "Trace width [mm]."},
            "B_mm": {
                "type": "number",
                "description": "Total dielectric thickness between both reference planes [mm].",
            },
            "er": {"type": "number", "description": "Substrate relative permittivity."},
            "T_mm": {"type": "number", "description": "Trace thickness [mm] (default 0.035 mm)."},
        },
        "required": ["W_mm", "B_mm", "er"],
    },
)


@register(_STRIPLINE_SYM_SPEC, write=False)
async def stackup_stripline_z0_symmetric(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = stripline_z0_symmetric(
        W_mm=a.get("W_mm"),
        B_mm=a.get("B_mm"),
        er=a.get("er"),
        T_mm=a.get("T_mm", 0.035),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. stackup_stripline_z0_asymmetric
# ═══════════════════════════════════════════════════════════════════════════════

_STRIPLINE_ASYM_SPEC = ToolSpec(
    name="stackup_stripline_z0_asymmetric",
    description=(
        "Compute asymmetric stripline Z0 [Ω] (trace at unequal distances from two planes).\n\n"
        "Model: Wadell §4.5 (eqn 4.5-3). Accurate within ~5% for c/b ∈ [0.5, 2.0].\n\n"
        "b = distance from trace to top reference plane [mm]\n"
        "c = distance from trace to bottom reference plane [mm]\n\n"
        "Input: { W_mm, b_mm, c_mm, er, T_mm? }\n"
        "Returns: { ok, Z0, er_eff, W_mm, b_mm, c_mm, er, T_mm }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "W_mm": {"type": "number", "description": "Trace width [mm]."},
            "b_mm": {"type": "number", "description": "Distance from trace to top reference plane [mm]."},
            "c_mm": {"type": "number", "description": "Distance from trace to bottom reference plane [mm]."},
            "er": {"type": "number", "description": "Substrate relative permittivity."},
            "T_mm": {"type": "number", "description": "Trace thickness [mm] (default 0.035 mm)."},
        },
        "required": ["W_mm", "b_mm", "c_mm", "er"],
    },
)


@register(_STRIPLINE_ASYM_SPEC, write=False)
async def stackup_stripline_z0_asymmetric(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = stripline_z0_asymmetric(
        W_mm=a.get("W_mm"),
        b_mm=a.get("b_mm"),
        c_mm=a.get("c_mm"),
        er=a.get("er"),
        T_mm=a.get("T_mm", 0.035),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. stackup_cpwg_z0
# ═══════════════════════════════════════════════════════════════════════════════

_CPWG_SPEC = ToolSpec(
    name="stackup_cpwg_z0",
    description=(
        "Compute coplanar-waveguide-with-ground (CPWG) characteristic impedance Z0 [Ω].\n\n"
        "Model: Hammerstad-Jensen conformal-mapping (Wadell §5.2) with Hilberg elliptic "
        "integral approximation.\n\n"
        "Input: { W_mm, G_mm, H_mm, er, T_mm? }\n"
        "where G_mm = gap between signal conductor and coplanar ground.\n"
        "Returns: { ok, Z0, er_eff, W_mm, G_mm, H_mm, er, T_mm }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "W_mm": {"type": "number", "description": "Signal conductor width [mm]."},
            "G_mm": {"type": "number", "description": "Gap to coplanar ground planes [mm]."},
            "H_mm": {"type": "number", "description": "Substrate height to back-side reference [mm]."},
            "er": {"type": "number", "description": "Substrate relative permittivity."},
            "T_mm": {"type": "number", "description": "Trace thickness [mm] (default 0.035 mm)."},
        },
        "required": ["W_mm", "G_mm", "H_mm", "er"],
    },
)


@register(_CPWG_SPEC, write=False)
async def stackup_cpwg_z0(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = cpwg_z0(
        W_mm=a.get("W_mm"),
        G_mm=a.get("G_mm"),
        H_mm=a.get("H_mm"),
        er=a.get("er"),
        T_mm=a.get("T_mm", 0.035),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. stackup_diff_microstrip_z0
# ═══════════════════════════════════════════════════════════════════════════════

_DIFF_MS_SPEC = ToolSpec(
    name="stackup_diff_microstrip_z0",
    description=(
        "Compute differential microstrip impedance Zdiff [Ω] (Wadell §3.7).\n\n"
        "Formula: Zdiff = 2 × Z0 × (1 − 0.347 × exp(−2.9 × S/H))\n"
        "where S = edge-to-edge spacing and Z0 = single-ended microstrip Z0.\n\n"
        "Typical 100 Ω differential pair on FR-4 (H=0.2 mm, er=4.3): "
        "W ≈ 0.18 mm, S ≈ 0.20 mm.\n\n"
        "Input: { W_mm, S_mm, H_mm, er, T_mm? }\n"
        "Returns: { ok, Z0_single, Zdiff, er_eff, W_mm, S_mm, H_mm, er, T_mm }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "W_mm": {"type": "number", "description": "Trace width [mm]."},
            "S_mm": {"type": "number", "description": "Edge-to-edge spacing between traces [mm]."},
            "H_mm": {"type": "number", "description": "Dielectric height [mm]."},
            "er": {"type": "number", "description": "Substrate relative permittivity."},
            "T_mm": {"type": "number", "description": "Trace thickness [mm] (default 0.035 mm)."},
        },
        "required": ["W_mm", "S_mm", "H_mm", "er"],
    },
)


@register(_DIFF_MS_SPEC, write=False)
async def stackup_diff_microstrip_z0(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = differential_microstrip_z0(
        W_mm=a.get("W_mm"),
        S_mm=a.get("S_mm"),
        H_mm=a.get("H_mm"),
        er=a.get("er"),
        T_mm=a.get("T_mm", 0.035),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. stackup_diff_stripline_z0
# ═══════════════════════════════════════════════════════════════════════════════

_DIFF_SL_SPEC = ToolSpec(
    name="stackup_diff_stripline_z0",
    description=(
        "Compute differential symmetric stripline impedance Zdiff [Ω] (Wadell §4.3).\n\n"
        "Formula: Zdiff = 2 × Z0 × (1 − 0.347 × exp(−2.9 × S/B))\n\n"
        "Input: { W_mm, S_mm, B_mm, er, T_mm? }\n"
        "Returns: { ok, Z0_single, Zdiff, er_eff, W_mm, S_mm, B_mm, er, T_mm }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "W_mm": {"type": "number", "description": "Trace width [mm]."},
            "S_mm": {"type": "number", "description": "Edge-to-edge spacing [mm]."},
            "B_mm": {"type": "number", "description": "Total dielectric thickness [mm]."},
            "er": {"type": "number", "description": "Substrate relative permittivity."},
            "T_mm": {"type": "number", "description": "Trace thickness [mm] (default 0.035 mm)."},
        },
        "required": ["W_mm", "S_mm", "B_mm", "er"],
    },
)


@register(_DIFF_SL_SPEC, write=False)
async def stackup_diff_stripline_z0(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = differential_stripline_z0(
        W_mm=a.get("W_mm"),
        S_mm=a.get("S_mm"),
        B_mm=a.get("B_mm"),
        er=a.get("er"),
        T_mm=a.get("T_mm", 0.035),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 9. stackup_effective_er
# ═══════════════════════════════════════════════════════════════════════════════

_EFF_ER_SPEC = ToolSpec(
    name="stackup_effective_er",
    description=(
        "Compute effective dielectric constant er_eff for a PCB transmission-line structure.\n\n"
        "Structures: 'microstrip', 'embedded_microstrip', 'stripline', 'cpwg'.\n\n"
        "Input: { structure, W_mm, H_mm, er, T_mm?, d_mm?, G_mm? }\n"
        "Returns: { ok, er_eff, structure, W_mm, H_mm, er }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "structure": {
                "type": "string",
                "enum": ["microstrip", "embedded_microstrip", "stripline", "cpwg"],
                "description": "Transmission-line structure type.",
            },
            "W_mm": {"type": "number", "description": "Trace width [mm]."},
            "H_mm": {
                "type": "number",
                "description": "Dielectric height (microstrip/CPWG) or total B (stripline) [mm].",
            },
            "er": {"type": "number", "description": "Substrate relative permittivity."},
            "T_mm": {"type": "number", "description": "Trace thickness [mm] (default 0.035 mm)."},
            "d_mm": {
                "type": "number",
                "description": "Cover layer thickness [mm] (embedded_microstrip only).",
            },
            "G_mm": {
                "type": "number",
                "description": "Gap to coplanar ground [mm] (CPWG only, default 0.1 mm).",
            },
        },
        "required": ["structure", "W_mm", "H_mm", "er"],
    },
)


@register(_EFF_ER_SPEC, write=False)
async def stackup_effective_er(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = effective_er(
        structure=a.get("structure", "microstrip"),
        W_mm=a.get("W_mm"),
        H_mm=a.get("H_mm"),
        er=a.get("er"),
        T_mm=a.get("T_mm", 0.035),
        d_mm=a.get("d_mm", 0.0),
        G_mm=a.get("G_mm", 0.1),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 10. stackup_propagation_delay
# ═══════════════════════════════════════════════════════════════════════════════

_PROP_DELAY_SPEC = ToolSpec(
    name="stackup_propagation_delay",
    description=(
        "Compute propagation delay Td [ps/mm] from effective dielectric constant.\n\n"
        "Formula: Td = sqrt(er_eff) / c  where c = 0.2998 mm/ps.\n\n"
        "Typical values:\n"
        "  Free space (er_eff=1): Td ≈ 3.33 ps/mm\n"
        "  FR-4 microstrip (er_eff≈3.0): Td ≈ 5.77 ps/mm\n"
        "  FR-4 stripline (er_eff=er=4.3): Td ≈ 6.95 ps/mm\n\n"
        "Input: { er_eff }\n"
        "Returns: { ok, er_eff, Td_ps_per_mm, Td_ns_per_m }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "er_eff": {
                "type": "number",
                "description": "Effective relative permittivity (from any Z0 function).",
            },
        },
        "required": ["er_eff"],
    },
)


@register(_PROP_DELAY_SPEC, write=False)
async def stackup_propagation_delay(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = propagation_delay_ps_per_mm(er_eff=a.get("er_eff"))
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 11. stackup_wavelength
# ═══════════════════════════════════════════════════════════════════════════════

_WAVELENGTH_SPEC = ToolSpec(
    name="stackup_wavelength",
    description=(
        "Compute guided wavelength λ [mm] on a transmission line at a given frequency.\n\n"
        "λ = c / (f × sqrt(er_eff))  where c = 299.792 mm/ns.\n\n"
        "Also returns λ/4 (quarter-wave stub length) and λ/10 (rule-of-thumb for "
        "distributed effects).\n\n"
        "Input: { freq_hz, er_eff }\n"
        "Returns: { ok, freq_hz, er_eff, wavelength_mm, quarter_wave_mm, tenth_wave_mm }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "freq_hz": {"type": "number", "description": "Frequency [Hz]."},
            "er_eff": {"type": "number", "description": "Effective relative permittivity."},
        },
        "required": ["freq_hz", "er_eff"],
    },
)


@register(_WAVELENGTH_SPEC, write=False)
async def stackup_wavelength(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = wavelength_mm(freq_hz=a.get("freq_hz"), er_eff=a.get("er_eff"))
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 12. stackup_trace_width_solver
# ═══════════════════════════════════════════════════════════════════════════════

_WIDTH_SOLVER_SPEC = ToolSpec(
    name="stackup_trace_width_solver",
    description=(
        "Solve for the trace width [mm] that achieves a target Z0 using bisection.\n\n"
        "Works for microstrip and symmetric stripline.\n"
        "Warns and sets unrealizable=True when the target Z0 cannot be achieved "
        "in the search range W ∈ [0.01, 20] mm.\n\n"
        "Input: { Z0_target, H_mm, er, structure?, T_mm?, B_mm? }\n"
        "Returns: { ok, W_mm, Z0_achieved, Z0_target, er_eff, iterations, unrealizable, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Z0_target": {"type": "number", "description": "Target characteristic impedance [Ω]."},
            "H_mm": {"type": "number", "description": "Dielectric height [mm]."},
            "er": {"type": "number", "description": "Substrate relative permittivity."},
            "structure": {
                "type": "string",
                "enum": ["microstrip", "stripline"],
                "description": "Transmission-line structure (default 'microstrip').",
            },
            "T_mm": {"type": "number", "description": "Trace thickness [mm] (default 0.035 mm)."},
            "B_mm": {
                "type": "number",
                "description": "Total dielectric thickness for stripline [mm] (overrides H_mm).",
            },
        },
        "required": ["Z0_target", "H_mm", "er"],
    },
)


@register(_WIDTH_SOLVER_SPEC, write=False)
async def stackup_trace_width_solver(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = trace_width_for_z0(
        Z0_target=a.get("Z0_target"),
        H_mm=a.get("H_mm"),
        er=a.get("er"),
        structure=a.get("structure", "microstrip"),
        T_mm=a.get("T_mm", 0.035),
        B_mm=a.get("B_mm"),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 13. stackup_diff_spacing_solver
# ═══════════════════════════════════════════════════════════════════════════════

_DIFF_SPACING_SPEC = ToolSpec(
    name="stackup_diff_spacing_solver",
    description=(
        "Solve for the trace spacing [mm] that achieves a target differential impedance "
        "Zdiff using bisection.\n\n"
        "Warns and sets unrealizable=True when the target cannot be achieved.\n\n"
        "Input: { Zdiff_target, W_mm, H_mm, er, structure?, T_mm?, B_mm? }\n"
        "Returns: { ok, S_mm, Zdiff_achieved, Zdiff_target, Z0_single, "
        "iterations, unrealizable, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Zdiff_target": {"type": "number", "description": "Target differential impedance [Ω]."},
            "W_mm": {"type": "number", "description": "Trace width [mm]."},
            "H_mm": {"type": "number", "description": "Dielectric height [mm]."},
            "er": {"type": "number", "description": "Substrate relative permittivity."},
            "structure": {
                "type": "string",
                "enum": ["microstrip", "stripline"],
                "description": "Transmission-line structure (default 'microstrip').",
            },
            "T_mm": {"type": "number", "description": "Trace thickness [mm] (default 0.035 mm)."},
            "B_mm": {
                "type": "number",
                "description": "Total dielectric thickness for stripline [mm].",
            },
        },
        "required": ["Zdiff_target", "W_mm", "H_mm", "er"],
    },
)


@register(_DIFF_SPACING_SPEC, write=False)
async def stackup_diff_spacing_solver(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = diff_pair_spacing_for_zdiff(
        Zdiff_target=a.get("Zdiff_target"),
        W_mm=a.get("W_mm"),
        H_mm=a.get("H_mm"),
        er=a.get("er"),
        structure=a.get("structure", "microstrip"),
        T_mm=a.get("T_mm", 0.035),
        B_mm=a.get("B_mm"),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 14. stackup_conductor_loss
# ═══════════════════════════════════════════════════════════════════════════════

_COND_LOSS_SPEC = ToolSpec(
    name="stackup_conductor_loss",
    description=(
        "Compute conductor (skin-effect) attenuation [dB/mm] vs frequency.\n\n"
        "Model: Hammerstad-Jensen (Wadell §3.5):\n"
        "  Rs = sqrt(π f μ₀ ρ)       [surface resistance Ω/sq]\n"
        "  αc = Rs / (π W Z0)        [Np/m → dB/mm]\n\n"
        "Surface roughness correction (Huray/IPC-2141A):\n"
        "  δs = sqrt(ρ / (π f μ₀))   [skin depth]\n"
        "  rough_factor = 1 + (2/π) × arctan(1.4 × (roughness/δs)²)\n\n"
        "Input: { freq_hz, W_mm, Z0, roughness_um?, rho_relative? }\n"
        "Returns: { ok, alpha_c_db_per_mm, alpha_c_rough_db_per_mm, "
        "skin_depth_um, roughness_factor, Rs_ohm_sq }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "freq_hz": {"type": "number", "description": "Frequency [Hz]."},
            "W_mm": {"type": "number", "description": "Trace width [mm]."},
            "Z0": {"type": "number", "description": "Characteristic impedance [Ω]."},
            "roughness_um": {
                "type": "number",
                "description": "RMS surface roughness [µm] (0 = ideal smooth, default 0).",
            },
            "rho_relative": {
                "type": "number",
                "description": "Resistivity relative to copper (default 1.0).",
            },
        },
        "required": ["freq_hz", "W_mm", "Z0"],
    },
)


@register(_COND_LOSS_SPEC, write=False)
async def stackup_conductor_loss(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = conductor_loss_db_per_mm(
        freq_hz=a.get("freq_hz"),
        W_mm=a.get("W_mm"),
        Z0=a.get("Z0"),
        roughness_um=a.get("roughness_um", 0.0),
        rho_relative=a.get("rho_relative", 1.0),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 15. stackup_dielectric_loss
# ═══════════════════════════════════════════════════════════════════════════════

_DIEL_LOSS_SPEC = ToolSpec(
    name="stackup_dielectric_loss",
    description=(
        "Compute dielectric (loss-tangent) attenuation [dB/mm] vs frequency.\n\n"
        "Model (Wadell §3.5):\n"
        "  αd = 27.3 × (er(er_eff−1)/(er_eff(er−1))) × tan_d × f_GHz / c_mm_ns\n\n"
        "For stripline (er_eff = er):\n"
        "  αd = 27.3 × tan_d × f_GHz / 299.792 dB/mm\n\n"
        "Typical FR-4 tan_d = 0.020 at 1 GHz.\n\n"
        "Input: { freq_hz, er, er_eff, tan_d }\n"
        "Returns: { ok, freq_hz, er, er_eff, tan_d, alpha_d_db_per_mm }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "freq_hz": {"type": "number", "description": "Frequency [Hz]."},
            "er": {"type": "number", "description": "Substrate relative permittivity."},
            "er_eff": {"type": "number", "description": "Effective relative permittivity."},
            "tan_d": {
                "type": "number",
                "description": "Loss tangent of the substrate (e.g. 0.020 for FR-4 at 1 GHz).",
            },
        },
        "required": ["freq_hz", "er", "er_eff", "tan_d"],
    },
)


@register(_DIEL_LOSS_SPEC, write=False)
async def stackup_dielectric_loss(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = dielectric_loss_db_per_mm(
        freq_hz=a.get("freq_hz"),
        er=a.get("er"),
        er_eff=a.get("er_eff"),
        tan_d=a.get("tan_d"),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 16. stackup_thickness
# ═══════════════════════════════════════════════════════════════════════════════

_THICKNESS_SPEC = ToolSpec(
    name="stackup_thickness",
    description=(
        "Compute total PCB thickness from a list of stackup layers.\n\n"
        "Each layer: { type: 'dielectric'|'copper', thickness_mm: float, name?: str }\n\n"
        "Returns total, copper, and dielectric thickness plus a layer-by-layer summary.\n\n"
        "Input: { layers: [{type, thickness_mm, name?}, ...] }\n"
        "Returns: { ok, total_thickness_mm, copper_thickness_mm, dielectric_thickness_mm, "
        "layer_count, layers_summary }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "layers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["dielectric", "copper"],
                            "description": "Layer material type.",
                        },
                        "thickness_mm": {
                            "type": "number",
                            "description": "Layer thickness [mm].",
                        },
                        "name": {
                            "type": "string",
                            "description": "Optional layer name (e.g. 'Core', 'L1-Cu').",
                        },
                    },
                    "required": ["type", "thickness_mm"],
                },
                "description": "Ordered list of stackup layers from top to bottom.",
            },
        },
        "required": ["layers"],
    },
)


@register(_THICKNESS_SPEC, write=False)
async def stackup_thickness(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = stackup_thickness_mm(layers=a.get("layers", []))
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 17. stackup_impedance_budget
# ═══════════════════════════════════════════════════════════════════════════════

_IMP_BUDGET_SPEC = ToolSpec(
    name="stackup_impedance_budget",
    description=(
        "Compute Z0 for every controlled-impedance net in a multilayer stackup "
        "and flag any that fall outside the impedance tolerance.\n\n"
        "Each net: { name, structure, W_mm, H_mm, er, T_mm?, S_mm?, target_z0? }\n"
        "structure: 'microstrip' | 'stripline' | 'differential_microstrip' | "
        "'differential_stripline'\n\n"
        "Warnings are issued (not raised) for any out-of-budget nets.\n\n"
        "Input: { nets: [...], tolerance_pct? }\n"
        "Returns: { ok, nets_results, all_in_budget, out_of_budget_names, tolerance_pct }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "nets": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "structure": {
                            "type": "string",
                            "enum": [
                                "microstrip",
                                "stripline",
                                "differential_microstrip",
                                "differential_stripline",
                            ],
                        },
                        "W_mm": {"type": "number"},
                        "H_mm": {"type": "number"},
                        "er": {"type": "number"},
                        "T_mm": {"type": "number"},
                        "S_mm": {"type": "number"},
                        "target_z0": {"type": "number"},
                    },
                    "required": ["name", "structure", "W_mm", "H_mm", "er"],
                },
                "description": "List of controlled-impedance nets to evaluate.",
            },
            "tolerance_pct": {
                "type": "number",
                "description": "Allowed deviation from target_z0 [%] (default 10%).",
            },
        },
        "required": ["nets"],
    },
)


@register(_IMP_BUDGET_SPEC, write=False)
async def stackup_impedance_budget_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = stackup_impedance_budget(
        nets=a.get("nets", []),
        tolerance_pct=a.get("tolerance_pct", 10.0),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# TOOLS export — consumed by plugin._register_tools
# ═══════════════════════════════════════════════════════════════════════════════

TOOLS = [
    (_COPPER_WEIGHT_SPEC.name,   _COPPER_WEIGHT_SPEC,   stackup_copper_weight),
    (_MICROSTRIP_Z0_SPEC.name,   _MICROSTRIP_Z0_SPEC,   stackup_microstrip_z0),
    (_EMB_MICROSTRIP_SPEC.name,  _EMB_MICROSTRIP_SPEC,  stackup_embedded_microstrip_z0),
    (_STRIPLINE_SYM_SPEC.name,   _STRIPLINE_SYM_SPEC,   stackup_stripline_z0_symmetric),
    (_STRIPLINE_ASYM_SPEC.name,  _STRIPLINE_ASYM_SPEC,  stackup_stripline_z0_asymmetric),
    (_CPWG_SPEC.name,            _CPWG_SPEC,            stackup_cpwg_z0),
    (_DIFF_MS_SPEC.name,         _DIFF_MS_SPEC,         stackup_diff_microstrip_z0),
    (_DIFF_SL_SPEC.name,         _DIFF_SL_SPEC,         stackup_diff_stripline_z0),
    (_EFF_ER_SPEC.name,          _EFF_ER_SPEC,          stackup_effective_er),
    (_PROP_DELAY_SPEC.name,      _PROP_DELAY_SPEC,      stackup_propagation_delay),
    (_WAVELENGTH_SPEC.name,      _WAVELENGTH_SPEC,      stackup_wavelength),
    (_WIDTH_SOLVER_SPEC.name,    _WIDTH_SOLVER_SPEC,    stackup_trace_width_solver),
    (_DIFF_SPACING_SPEC.name,    _DIFF_SPACING_SPEC,    stackup_diff_spacing_solver),
    (_COND_LOSS_SPEC.name,       _COND_LOSS_SPEC,       stackup_conductor_loss),
    (_DIEL_LOSS_SPEC.name,       _DIEL_LOSS_SPEC,       stackup_dielectric_loss),
    (_THICKNESS_SPEC.name,       _THICKNESS_SPEC,       stackup_thickness),
    (_IMP_BUDGET_SPEC.name,      _IMP_BUDGET_SPEC,      stackup_impedance_budget_tool),
]
