"""
kerf_cad_core.fasteners.tools — LLM tool wrappers for bolted-joint analysis.

Registers nine tools with the Kerf tool registry:

  bolt_preload_from_torque    — clamp preload from tightening torque (T = K·F·d)
  bolt_stiffness              — bolt axial stiffness (shank + threaded series)
  clamped_member_stiffness    — clamped-member stiffness via frustum (VDI 2230)
  bolt_joint_load_factor      — joint diagram load factor Φ
  bolt_working_stress         — combined tensile + torsional working stress
  bolt_separation_safety      — joint separation safety factor
  bolt_slip_safety            — friction-grip slip safety factor
  bolt_fatigue_check          — alternating stress vs endurance (Goodman)
  bolt_strip_length           — thread stripping engagement length

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": False, "reason": "..."} — tools never raise.

References
----------
VDI 2230-1:2015 — Systematic calculation of highly stressed bolted joints
Shigley's Mechanical Engineering Design, 10th ed., Chapter 8

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.fasteners.joint import (
    preload_from_torque,
    bolt_stiffness,
    clamped_stiffness,
    joint_load_factor,
    bolt_working_stress,
    separation_safety,
    slip_safety,
    fatigue_check,
    strip_length,
)


# ---------------------------------------------------------------------------
# Tool: bolt_preload_from_torque
# ---------------------------------------------------------------------------

_preload_spec = ToolSpec(
    name="bolt_preload_from_torque",
    description=(
        "Compute the clamp preload force from a tightening torque using the "
        "nut-factor model: T = K · F · d  →  F = T / (K · d).\n"
        "\n"
        "Typical nut factors K: 0.10–0.15 (lubricated/waxed), "
        "0.18–0.22 (dry steel on steel), 0.25–0.30 (zinc-plated, rough).\n"
        "\n"
        "Returns F_preload_N (Newtons).\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "T": {
                "type": "number",
                "description": "Tightening torque (N·m). Must be > 0.",
            },
            "d": {
                "type": "number",
                "description": "Nominal bolt diameter (m). Must be > 0.",
            },
            "K": {
                "type": "number",
                "description": (
                    "Nut factor / torque coefficient (dimensionless). "
                    "Default 0.20 (dry steel).  Typical range 0.10–0.35."
                ),
            },
        },
        "required": ["T", "d"],
    },
)


@register(_preload_spec, write=False)
async def run_bolt_preload_from_torque(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("T") is None:
        return json.dumps({"ok": False, "reason": "T is required"})
    if a.get("d") is None:
        return json.dumps({"ok": False, "reason": "d is required"})

    kwargs: dict = {}
    if "K" in a:
        kwargs["K"] = a["K"]

    result = preload_from_torque(a["T"], a["d"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: bolt_stiffness
# ---------------------------------------------------------------------------

_bolt_stiffness_spec = ToolSpec(
    name="bolt_stiffness",
    description=(
        "Compute bolt axial stiffness treating the bolt as shank + threaded "
        "segment in series.  k_i = E·A_i/L_i; 1/k_bolt = 1/k_shank + 1/k_thread.\n"
        "\n"
        "For a fully-threaded bolt pass length_shank=0.\n"
        "Use d_thread_minor = minor (stress-area) diameter from the ISO thread table.\n"
        "\n"
        "Returns k_bolt_N_per_m (N/m).\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "d_shank": {
                "type": "number",
                "description": "Unthreaded shank diameter (m). Must be > 0.",
            },
            "length_shank": {
                "type": "number",
                "description": "Length of unthreaded shank within grip (m). Must be >= 0.",
            },
            "d_thread_minor": {
                "type": "number",
                "description": "Minor/stress-area diameter of threaded section (m). Must be > 0.",
            },
            "length_thread": {
                "type": "number",
                "description": "Length of threaded section within grip (m). Must be > 0.",
            },
            "E_bolt": {
                "type": "number",
                "description": "Young's modulus of bolt material (Pa). Default 200e9 (steel).",
            },
        },
        "required": ["d_shank", "length_shank", "d_thread_minor", "length_thread"],
    },
)


@register(_bolt_stiffness_spec, write=False)
async def run_bolt_stiffness(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("d_shank", "length_shank", "d_thread_minor", "length_thread"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "E_bolt" in a:
        kwargs["E_bolt"] = a["E_bolt"]

    result = bolt_stiffness(
        a["d_shank"], a["length_shank"], a["d_thread_minor"], a["length_thread"],
        **kwargs,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: clamped_member_stiffness
# ---------------------------------------------------------------------------

_clamp_stiff_spec = ToolSpec(
    name="clamped_member_stiffness",
    description=(
        "Compute clamped-member axial stiffness using the conical-frustum model "
        "(VDI 2230 Annex A / Shigley eq. 8-23).  The frustum half-angle is "
        "30° by default (VDI recommendation).\n"
        "\n"
        "Returns k_clamp_N_per_m (N/m).\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "grip_length": {
                "type": "number",
                "description": "Total clamped-member grip length (m). Must be > 0.",
            },
            "E_clamp": {
                "type": "number",
                "description": (
                    "Effective Young's modulus of clamped members (Pa). Must be > 0. "
                    "Steel ≈ 200e9 Pa; aluminium ≈ 70e9 Pa."
                ),
            },
            "d_bolt": {
                "type": "number",
                "description": "Nominal bolt diameter (m). Must be > 0.",
            },
            "half_angle_deg": {
                "type": "number",
                "description": "Frustum half-angle α (degrees). Default 30° (VDI 2230).",
            },
        },
        "required": ["grip_length", "E_clamp", "d_bolt"],
    },
)


@register(_clamp_stiff_spec, write=False)
async def run_clamped_member_stiffness(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("grip_length", "E_clamp", "d_bolt"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "half_angle_deg" in a:
        kwargs["half_angle_deg"] = a["half_angle_deg"]

    result = clamped_stiffness(a["grip_length"], a["E_clamp"], a["d_bolt"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: bolt_joint_load_factor
# ---------------------------------------------------------------------------

_load_factor_spec = ToolSpec(
    name="bolt_joint_load_factor",
    description=(
        "Compute joint load factor Φ = k_bolt / (k_bolt + k_clamp).\n"
        "\n"
        "Φ is the fraction of external load borne by the bolt; "
        "(1−Φ) relieves the clamp preload.  Typical: 0.05–0.25 for stiff steel "
        "joints; 0.4–0.8 for gaskets.\n"
        "\n"
        "Returns Phi (dimensionless).\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "k_bolt": {
                "type": "number",
                "description": "Bolt axial stiffness (N/m). Must be > 0.",
            },
            "k_clamp": {
                "type": "number",
                "description": "Clamped-member stiffness (N/m). Must be > 0.",
            },
        },
        "required": ["k_bolt", "k_clamp"],
    },
)


@register(_load_factor_spec, write=False)
async def run_bolt_joint_load_factor(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("k_bolt", "k_clamp"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = joint_load_factor(a["k_bolt"], a["k_clamp"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: bolt_working_stress
# ---------------------------------------------------------------------------

_working_stress_spec = ToolSpec(
    name="bolt_working_stress",
    description=(
        "Compute total bolt tensile stress from preload + working load, "
        "plus optional torsional stress from residual wrench torque.\n"
        "\n"
        "F_bolt = F_preload + Φ·F_external\n"
        "σ_total = Kb · F_bolt / A_stress\n"
        "Von Mises: σ_VM = √(σ² + 3τ²)\n"
        "\n"
        "Returns sigma_total_Pa, sigma_von_mises_Pa.\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "F_preload": {
                "type": "number",
                "description": "Assembly preload (N). Must be > 0.",
            },
            "F_external": {
                "type": "number",
                "description": "External separating load per bolt (N). Must be >= 0.",
            },
            "Phi": {
                "type": "number",
                "description": "Joint load factor (0 < Φ ≤ 1).",
            },
            "A_stress": {
                "type": "number",
                "description": (
                    "Bolt tensile stress area (m²). Must be > 0. "
                    "From ISO thread table (convert mm² × 1e-6 → m²)."
                ),
            },
            "Kb": {
                "type": "number",
                "description": "Bending stress concentration factor (default 1.0).",
            },
            "torque_Nm": {
                "type": "number",
                "description": "Residual wrench torque on bolt body (N·m). Default 0.",
            },
            "d_m": {
                "type": "number",
                "description": "Mean (pitch) bolt diameter (m). Required if torque_Nm > 0.",
            },
        },
        "required": ["F_preload", "F_external", "Phi", "A_stress"],
    },
)


@register(_working_stress_spec, write=False)
async def run_bolt_working_stress(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("F_preload", "F_external", "Phi", "A_stress"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "Kb" in a:
        kwargs["Kb"] = a["Kb"]
    if "torque_Nm" in a:
        kwargs["torque_Nm"] = a["torque_Nm"]
    if "d_m" in a:
        kwargs["d_m"] = a["d_m"]

    result = bolt_working_stress(
        a["F_preload"], a["F_external"], a["Phi"], a["A_stress"], **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: bolt_separation_safety
# ---------------------------------------------------------------------------

_sep_safety_spec = ToolSpec(
    name="bolt_separation_safety",
    description=(
        "Compute joint separation safety factor.\n"
        "\n"
        "n_sep = F_preload / [F_external · (1 − Φ)]\n"
        "\n"
        "n_sep < 1.0 → joint opens (separation failure, warns).\n"
        "n_sep < 1.2 → marginal (warns).\n"
        "\n"
        "Returns n_sep and separated flag.\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "F_preload": {
                "type": "number",
                "description": "Assembly preload (N). Must be > 0.",
            },
            "F_external": {
                "type": "number",
                "description": "External separating load per bolt (N). Must be > 0.",
            },
            "Phi": {
                "type": "number",
                "description": "Joint load factor (0 ≤ Φ < 1).",
            },
        },
        "required": ["F_preload", "F_external", "Phi"],
    },
)


@register(_sep_safety_spec, write=False)
async def run_bolt_separation_safety(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("F_preload", "F_external", "Phi"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = separation_safety(a["F_preload"], a["F_external"], a["Phi"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: bolt_slip_safety
# ---------------------------------------------------------------------------

_slip_safety_spec = ToolSpec(
    name="bolt_slip_safety",
    description=(
        "Compute friction-grip slip safety factor for a shear joint.\n"
        "\n"
        "n_slip = μ · F_preload · n_bolts / F_shear\n"
        "\n"
        "n_slip < 1.0 → joint slips (warns).\n"
        "n_slip < 1.25 → below structural minimum (warns).\n"
        "\n"
        "Returns n_slip and slips flag.\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "F_preload": {
                "type": "number",
                "description": "Assembly preload per bolt (N). Must be > 0.",
            },
            "F_shear": {
                "type": "number",
                "description": "Total applied shear force on joint (N). Must be > 0.",
            },
            "mu": {
                "type": "number",
                "description": (
                    "Coefficient of friction between faying surfaces. Must be > 0. "
                    "Typical: 0.35 (clean steel), 0.50 (shot-blasted)."
                ),
            },
            "n_bolts": {
                "type": "integer",
                "description": "Number of bolts in the joint (default 1). Must be >= 1.",
            },
        },
        "required": ["F_preload", "F_shear", "mu"],
    },
)


@register(_slip_safety_spec, write=False)
async def run_bolt_slip_safety(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("F_preload", "F_shear", "mu"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "n_bolts" in a:
        kwargs["n_bolts"] = a["n_bolts"]

    result = slip_safety(a["F_preload"], a["F_shear"], a["mu"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: bolt_fatigue_check
# ---------------------------------------------------------------------------

_fatigue_spec = ToolSpec(
    name="bolt_fatigue_check",
    description=(
        "Modified-Goodman fatigue check for a bolt under cyclic loading.\n"
        "\n"
        "Kf·σ_a/Se + σ_m/Sut ≤ 1 for infinite life.\n"
        "\n"
        "σ_a = alternating amplitude = Φ·F_ext / (2·A_stress)\n"
        "σ_m = mean = (F_preload + Φ·F_ext/2) / A_stress\n"
        "\n"
        "Returns goodman_ratio, fatigue_ok, n_goodman.\n"
        "Warns if ratio > 1.0 (failure) or > 0.8 (marginal).\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "sigma_a": {
                "type": "number",
                "description": "Alternating bolt stress amplitude (Pa). Must be >= 0.",
            },
            "Se": {
                "type": "number",
                "description": "Bolt endurance limit (Pa). Must be > 0.",
            },
            "sigma_m": {
                "type": "number",
                "description": "Mean bolt stress (Pa). Must be >= 0.",
            },
            "Sut": {
                "type": "number",
                "description": "Bolt ultimate tensile strength (Pa). Must be > 0.",
            },
            "Kf": {
                "type": "number",
                "description": (
                    "Fatigue stress concentration factor for thread root (default 1.0). "
                    "Typical bolt threads: Kf ≈ 2.2–3.8."
                ),
            },
        },
        "required": ["sigma_a", "Se", "sigma_m", "Sut"],
    },
)


@register(_fatigue_spec, write=False)
async def run_bolt_fatigue_check(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("sigma_a", "Se", "sigma_m", "Sut"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "Kf" in a:
        kwargs["Kf"] = a["Kf"]

    result = fatigue_check(a["sigma_a"], a["Se"], a["sigma_m"], a["Sut"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: bolt_strip_length
# ---------------------------------------------------------------------------

_strip_spec = ToolSpec(
    name="bolt_strip_length",
    description=(
        "Compute minimum thread engagement length to prevent thread stripping "
        "(bolt external thread and nut/tapped-hole internal thread).\n"
        "\n"
        "Uses Shigley §8-7 shear-area approach.  Returns L_e_required_m "
        "(including safety factor).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "F_preload": {
                "type": "number",
                "description": "Assembly preload (N). Must be > 0.",
            },
            "F_external": {
                "type": "number",
                "description": "External working load (N). Must be >= 0.",
            },
            "Phi": {
                "type": "number",
                "description": "Joint load factor (0 < Φ ≤ 1).",
            },
            "d_nom": {
                "type": "number",
                "description": "Nominal bolt diameter (m). Must be > 0.",
            },
            "thread_pitch": {
                "type": "number",
                "description": "Thread pitch (m). E.g. M16 pitch=2 mm → 0.002 m. Must be > 0.",
            },
            "Ssy_bolt": {
                "type": "number",
                "description": "Shear yield strength of bolt material (Pa). Must be > 0.",
            },
            "Ssy_nut": {
                "type": "number",
                "description": (
                    "Shear yield strength of nut/tapped material (Pa). Must be > 0. "
                    "For tapped aluminium typically ≈ 0.577 × Sy_al."
                ),
            },
            "safety_factor": {
                "type": "number",
                "description": "Safety factor on engagement length (default 2.0).",
            },
        },
        "required": [
            "F_preload", "F_external", "Phi",
            "d_nom", "thread_pitch", "Ssy_bolt", "Ssy_nut",
        ],
    },
)


@register(_strip_spec, write=False)
async def run_bolt_strip_length(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    required = [
        "F_preload", "F_external", "Phi",
        "d_nom", "thread_pitch", "Ssy_bolt", "Ssy_nut",
    ]
    for field in required:
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "safety_factor" in a:
        kwargs["safety_factor"] = a["safety_factor"]

    result = strip_length(
        a["F_preload"], a["F_external"], a["Phi"],
        a["d_nom"], a["thread_pitch"], a["Ssy_bolt"], a["Ssy_nut"],
        **kwargs,
    )
    return ok_payload(result)
