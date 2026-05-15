"""
Eye-diagram and jitter-budget tools for the Kerf electronics plugin.

Provides three LLM-facing tools:

  eye_estimate   — first-order statistical eye diagram from a channel model
  jitter_budget  — Tj = Dj + 2·Rj·Q(BER) decomposition
  eye_mask_check — pass/fail against a rectangular eye mask

All computation is delegated to kerf_electronics.eye.model (pure math,
no I/O, no network).  This file is purely the tool/JSON layer.

Physical references: see kerf_electronics.eye.model module docstring
(Johnson & Graham 2003; Bogatin 2004; Li 2007).

Author: imranparuk
"""

from __future__ import annotations

import json
from typing import Any

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register

from kerf_electronics.eye.model import (
    eye_estimate as _eye_estimate,
    jitter_budget as _jitter_budget,
    eye_mask_check as _eye_mask_check,
)


# ──────────────────────────────────────────────────────────────────────────────
# Helper
# ──────────────────────────────────────────────────────────────────────────────

def _num(val: Any, name: str, required: bool = True, default: float | None = None):
    """Return (float, None) or (None, error_string)."""
    if val is None:
        if required:
            return None, f"{name} is required"
        return default, None
    if not isinstance(val, (int, float)):
        return None, f"{name} must be a number, got {val!r}"
    return float(val), None


# ──────────────────────────────────────────────────────────────────────────────
# 1. eye_estimate
# ──────────────────────────────────────────────────────────────────────────────

_EYE_ESTIMATE_SPEC = ToolSpec(
    name="eye_estimate",
    description=(
        "Compute a first-order statistical eye diagram for a lossy PCB serial channel. "
        "Returns normalised eye height (vertical opening), eye width in UI, vertical eye "
        "closure (VEC), horizontal eye closure (HEC), total insertion loss, attenuation, "
        "received rise time, and intermediate details. "
        "Channel model: insertion-loss at Nyquist sets attenuation; ISI and reflections "
        "add vertical penalty; channel bandwidth widens the received rise time. "
        "References: Johnson & Graham 2003 §3.4/§3.7; Bogatin 2004 §7. "
        "Input shape: { loss_db_per_inch, length_inch, bit_rate_bps, rise_time_tx_s, "
        "isi_fraction?, reflection_gamma? }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "loss_db_per_inch": {
                "type": "number",
                "description": (
                    "Insertion loss at Nyquist frequency [dB/inch]. "
                    "Typical FR4: 0.3–0.8 dB/inch at 5 GHz."
                ),
            },
            "length_inch": {
                "type": "number",
                "description": "Channel (trace) length [inches].",
            },
            "bit_rate_bps": {
                "type": "number",
                "description": "Signalling bit rate [bits/s], e.g. 10e9 for 10 Gbps.",
            },
            "rise_time_tx_s": {
                "type": "number",
                "description": (
                    "Transmitter 10–90% rise time [seconds], e.g. 50e-12 for 50 ps."
                ),
            },
            "isi_fraction": {
                "type": "number",
                "description": (
                    "Fractional ISI penalty relative to ideal eye height (0–<1). "
                    "Default: 0.05 (5%). Use 0 for an ideal channel."
                ),
            },
            "reflection_gamma": {
                "type": "number",
                "description": (
                    "Magnitude of the dominant reflection coefficient |Γ| (0–1). "
                    "Default: 0.0 (no reflections). "
                    "Obtain via si_impedance + reflection coefficient formula."
                ),
            },
        },
        "required": ["loss_db_per_inch", "length_inch", "bit_rate_bps", "rise_time_tx_s"],
    },
)


@register(_EYE_ESTIMATE_SPEC, write=False)
async def eye_estimate(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    ldi, e = _num(a.get("loss_db_per_inch"), "loss_db_per_inch")
    if e:
        return err_payload(e, "BAD_ARGS")
    li, e = _num(a.get("length_inch"), "length_inch")
    if e:
        return err_payload(e, "BAD_ARGS")
    br, e = _num(a.get("bit_rate_bps"), "bit_rate_bps")
    if e:
        return err_payload(e, "BAD_ARGS")
    rt, e = _num(a.get("rise_time_tx_s"), "rise_time_tx_s")
    if e:
        return err_payload(e, "BAD_ARGS")

    isi, e = _num(a.get("isi_fraction"), "isi_fraction", required=False, default=0.05)
    if e:
        return err_payload(e, "BAD_ARGS")
    gamma, e = _num(a.get("reflection_gamma"), "reflection_gamma", required=False, default=0.0)
    if e:
        return err_payload(e, "BAD_ARGS")

    result = _eye_estimate(
        loss_db_per_inch=ldi,
        length_inch=li,
        bit_rate_bps=br,
        rise_time_tx_s=rt,
        isi_fraction=isi,
        reflection_gamma=gamma,
    )

    if not result.get("ok"):
        return err_payload(result.get("reason", "eye_estimate failed"), "BAD_ARGS")

    return ok_payload(result)


# ──────────────────────────────────────────────────────────────────────────────
# 2. jitter_budget
# ──────────────────────────────────────────────────────────────────────────────

_JITTER_BUDGET_SPEC = ToolSpec(
    name="jitter_budget",
    description=(
        "Compute total jitter (Tj) decomposition: Tj = Dj + 2·Rj·Q(BER). "
        "Rj is random jitter (1-sigma, Gaussian); Dj is deterministic jitter (peak-to-peak). "
        "Q(BER) is the Q-factor for the target bit-error ratio. "
        "Inputs may be in any consistent unit (seconds, ps, UI). "
        "Reference: Li, 'Jitter, Noise, and Signal Integrity at High-Speed', "
        "Prentice Hall 2007, §2.3 eq. 2-6. "
        "Input shape: { rj_s, dj_s, ber? }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "rj_s": {
                "type": "number",
                "description": (
                    "Random jitter 1-sigma value. "
                    "May be in seconds, ps, or UI — consistent with dj_s."
                ),
            },
            "dj_s": {
                "type": "number",
                "description": (
                    "Deterministic jitter peak-to-peak value (same unit as rj_s). "
                    "Must be >= 0."
                ),
            },
            "ber": {
                "type": "number",
                "description": (
                    "Target bit-error ratio, e.g. 1e-12 for telecom grade. "
                    "Must be in (0, 0.5). Default: 1e-12."
                ),
            },
        },
        "required": ["rj_s", "dj_s"],
    },
)


@register(_JITTER_BUDGET_SPEC, write=False)
async def jitter_budget(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    rj, e = _num(a.get("rj_s"), "rj_s")
    if e:
        return err_payload(e, "BAD_ARGS")
    dj, e = _num(a.get("dj_s"), "dj_s", required=False, default=0.0)
    if e:
        return err_payload(e, "BAD_ARGS")

    ber_raw = a.get("ber")
    if ber_raw is None:
        ber = 1e-12
    else:
        ber, e = _num(ber_raw, "ber")
        if e:
            return err_payload(e, "BAD_ARGS")

    result = _jitter_budget(rj_s=rj, dj_s=dj, ber=ber)

    if not result.get("ok"):
        return err_payload(result.get("reason", "jitter_budget failed"), "BAD_ARGS")

    return ok_payload(result)


# ──────────────────────────────────────────────────────────────────────────────
# 3. eye_mask_check
# ──────────────────────────────────────────────────────────────────────────────

_EYE_MASK_CHECK_SPEC = ToolSpec(
    name="eye_mask_check",
    description=(
        "Check whether a computed eye diagram passes a rectangular eye mask. "
        "The eye passes when eye_height >= mask height AND eye_width_ui >= mask width. "
        "An optional vertical offset reduces the effective eye height. "
        "Returns pass/fail, height margin, and width margin. "
        "Input shape: { eye: <eye_estimate result>, mask: { height, width_ui, voffset? } }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "eye": {
                "type": "object",
                "description": (
                    "Eye diagram result dict from eye_estimate tool "
                    "(must contain 'ok', 'eye_height', 'eye_width_ui')."
                ),
            },
            "mask": {
                "type": "object",
                "description": (
                    "Rectangular mask definition: "
                    "{ 'height': <min eye height>, "
                    "'width_ui': <min eye width in UI>, "
                    "'voffset': <optional vertical centre offset> }."
                ),
                "properties": {
                    "height": {
                        "type": "number",
                        "description": "Minimum required eye height (normalised, >= 0).",
                    },
                    "width_ui": {
                        "type": "number",
                        "description": "Minimum required eye width [UI] (>= 0).",
                    },
                    "voffset": {
                        "type": "number",
                        "description": "Vertical offset of mask centre (default: 0.0).",
                    },
                },
                "required": ["height", "width_ui"],
            },
        },
        "required": ["eye", "mask"],
    },
)


@register(_EYE_MASK_CHECK_SPEC, write=False)
async def eye_mask_check(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    eye = a.get("eye")
    mask = a.get("mask")

    if eye is None:
        return err_payload("'eye' is required", "BAD_ARGS")
    if mask is None:
        return err_payload("'mask' is required", "BAD_ARGS")
    if not isinstance(eye, dict):
        return err_payload("'eye' must be an object", "BAD_ARGS")
    if not isinstance(mask, dict):
        return err_payload("'mask' must be an object", "BAD_ARGS")

    result = _eye_mask_check(eye=eye, mask=mask)

    if not result.get("ok"):
        return err_payload(result.get("reason", "eye_mask_check failed"), "BAD_ARGS")

    return ok_payload(result)


# ──────────────────────────────────────────────────────────────────────────────
# TOOLS export — consumed by plugin._register_tools
# ──────────────────────────────────────────────────────────────────────────────

TOOLS = [
    (_EYE_ESTIMATE_SPEC.name,    _EYE_ESTIMATE_SPEC,    eye_estimate),
    (_JITTER_BUDGET_SPEC.name,   _JITTER_BUDGET_SPEC,   jitter_budget),
    (_EYE_MASK_CHECK_SPEC.name,  _EYE_MASK_CHECK_SPEC,  eye_mask_check),
]
