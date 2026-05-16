"""
kerf_cad_core.beltchain.tools — LLM tool wrappers for belt & chain drive selection.

Registers three tools with the Kerf tool registry:

  vbelt_design
      Classical / narrow V-belt drive: design power, belt selection, length,
      wrap angles, number of belts, capstan tensions, shaft load.

  timing_belt_design
      Synchronous (timing) belt drive: pitch, teeth-in-mesh, width selection,
      belt pitch length, centre distance.

  chain_drive_design
      ANSI roller-chain drive: pitch selection, sprocket pitch diameters,
      chain length in pitches (even), rated power, lubrication regime,
      breaking-load safety factor.

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
Shigley's Mechanical Engineering Design, 10th ed., §§ 17-1 to 17-12
ANSI/RMA IP-20 — Classical and Narrow V-Belt Engineering Standard
ANSI/ASME B29.1 — Precision Power Transmission Roller Chains

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.beltchain.drives import (
    vbelt_design,
    timing_belt_design,
    chain_drive_design,
)


# ---------------------------------------------------------------------------
# Tool: vbelt_design
# ---------------------------------------------------------------------------

_vbelt_design_spec = ToolSpec(
    name="vbelt_design",
    description=(
        "Design a classical or narrow V-belt drive.\n"
        "\n"
        "Computes:\n"
        "  • Design power (nominal × service factor Ks)\n"
        "  • Belt cross-section recommendation (A/B/C/D/3V/5V/8V)\n"
        "  • Large-sheave diameter from speed ratio\n"
        "  • Belt speed (m/s) with out-of-range warning\n"
        "  • Pitch belt length (mm) and centre distance (mm)\n"
        "  • Wrap angles on both sheaves; warning if small-sheave < 120°\n"
        "  • Wrap-angle correction Cv and length correction Kc\n"
        "  • Corrected per-belt rated power (kW)\n"
        "  • Number of belts required (ceiling)\n"
        "  • Tight/slack tensions via capstan e^(μθ) equation (N)\n"
        "  • Total shaft load = n_belts × (T1 + T2) (N)\n"
        "\n"
        "Warnings (never fatal): wrap angle < 120°, speed out of range, "
        "undersized drive.\n"
        "\n"
        "References: Shigley §17-5, RMA IP-20.\n"
        "Errors → {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "power_kW": {
                "type": "number",
                "description": "Nominal transmitted power (kW). Must be > 0.",
            },
            "n_driver_rpm": {
                "type": "number",
                "description": "Driver (small) sheave speed (rpm). Must be > 0.",
            },
            "n_driven_rpm": {
                "type": "number",
                "description": "Driven (large) sheave speed (rpm). Must be > 0.",
            },
            "d_small_mm": {
                "type": "number",
                "description": (
                    "Pitch diameter of small (driver) sheave (mm). "
                    "If omitted, chosen from belt section minimum. Must be > 0."
                ),
            },
            "center_distance_mm": {
                "type": "number",
                "description": (
                    "Desired centre distance (mm). "
                    "If omitted, defaults to D_large + d_small (rule of thumb). "
                    "Must be > 0."
                ),
            },
            "service_factor": {
                "type": "number",
                "description": (
                    "Manual override for service factor Ks. "
                    "If omitted, looked up from driver_type × load_hours. "
                    "Must be > 0."
                ),
            },
            "driver_type": {
                "type": "string",
                "enum": ["normal", "heavy"],
                "description": (
                    "'normal' = AC motor normal torque (default). "
                    "'heavy' = high-torque motor or single-cylinder IC engine."
                ),
            },
            "load_hours": {
                "type": "string",
                "enum": ["light", "moderate", "heavy"],
                "description": (
                    "Daily operating hours: "
                    "'light' < 10 h/day, 'moderate' 10-16 h/day (default), 'heavy' > 16 h/day."
                ),
            },
            "mu": {
                "type": "number",
                "description": (
                    "Coefficient of friction between belt and sheave. "
                    "Default 0.51 (rubber on cast iron). Must be > 0."
                ),
            },
        },
        "required": ["power_kW", "n_driver_rpm", "n_driven_rpm"],
    },
)


@register(_vbelt_design_spec, write=False)
async def run_vbelt_design(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("power_kW", "n_driver_rpm", "n_driven_rpm"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("d_small_mm", "center_distance_mm", "service_factor",
                "driver_type", "load_hours", "mu"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = vbelt_design(a["power_kW"], a["n_driver_rpm"], a["n_driven_rpm"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: timing_belt_design
# ---------------------------------------------------------------------------

_timing_belt_design_spec = ToolSpec(
    name="timing_belt_design",
    description=(
        "Design a synchronous (timing) belt drive.\n"
        "\n"
        "Computes:\n"
        "  • Belt pitch selection (MXL/3M/5M/8M/14M/H) from design power\n"
        "  • Driver and driven sprocket tooth counts from speed ratio\n"
        "  • Pitch diameters: d = z·p/π\n"
        "  • Belt speed (m/s)\n"
        "  • Belt pitch length (mm) and centre distance (mm)\n"
        "  • Teeth in mesh on small sprocket; warning if < 6\n"
        "  • Minimum belt width (mm) rounded to next standard size\n"
        "\n"
        "Warnings: teeth_in_mesh < 6, required width exceeds catalogue max.\n"
        "\n"
        "References: Shigley §17-9.\n"
        "Errors → {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "power_kW": {
                "type": "number",
                "description": "Nominal transmitted power (kW). Must be > 0.",
            },
            "n_driver_rpm": {
                "type": "number",
                "description": "Driver sprocket speed (rpm). Must be > 0.",
            },
            "pitch_mm": {
                "type": "number",
                "description": (
                    "Belt pitch (mm). Standard values: 2.032 (MXL), 3 (3M), "
                    "5 (5M), 8 (8M), 14 (14M), 25.4 (H). "
                    "If omitted, auto-selected from design power."
                ),
            },
            "z_driver": {
                "type": "integer",
                "description": "Driver sprocket tooth count. Default 18. Must be >= 10.",
            },
            "speed_ratio": {
                "type": "number",
                "description": (
                    "Speed ratio n_driver / n_driven (>= 1). Default 1.0 (1:1). "
                    "Values < 1 are interpreted as n_driven/n_driver and inverted."
                ),
            },
            "center_distance_mm": {
                "type": "number",
                "description": (
                    "Desired centre distance (mm). "
                    "If omitted, defaults to 3 × large pitch diameter. "
                    "Must be > 0."
                ),
            },
            "service_factor": {
                "type": "number",
                "description": "Design service factor Ks. Default 1.3. Must be > 0.",
            },
        },
        "required": ["power_kW", "n_driver_rpm"],
    },
)


@register(_timing_belt_design_spec, write=False)
async def run_timing_belt_design(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("power_kW", "n_driver_rpm"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("pitch_mm", "z_driver", "speed_ratio", "center_distance_mm", "service_factor"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = timing_belt_design(a["power_kW"], a["n_driver_rpm"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: chain_drive_design
# ---------------------------------------------------------------------------

_chain_drive_design_spec = ToolSpec(
    name="chain_drive_design",
    description=(
        "Design an ANSI roller-chain drive.\n"
        "\n"
        "Computes:\n"
        "  • ANSI chain number selection (25/35/40/50/60/80/100/120/140/160/180/200/240)\n"
        "  • Service-factor design power = power × Ks\n"
        "  • Sprocket pitch diameters: d = p / sin(π/z)\n"
        "  • Chain speed (m/s)\n"
        "  • Chain length in pitches (even integer, rounded up)\n"
        "  • Centre distance (mm) computed from even chain length\n"
        "  • Rated power per strand and total multi-strand rated power (kW)\n"
        "  • Working tension and breaking-load safety factor\n"
        "  • Lubrication regime: type_A_drip / type_B_bath / type_C_pump\n"
        "\n"
        "Warnings: safety factor < 7, over-speed, undersized capacity, "
        "pump lubrication required.\n"
        "\n"
        "References: Shigley §17-11, ANSI B29.1.\n"
        "Errors → {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "power_kW": {
                "type": "number",
                "description": "Nominal transmitted power (kW). Must be > 0.",
            },
            "n_small_rpm": {
                "type": "number",
                "description": "Small sprocket speed (rpm). Must be > 0.",
            },
            "z_small": {
                "type": "integer",
                "description": "Teeth on small sprocket. Must be >= 7 (ANSI minimum).",
            },
            "z_large": {
                "type": "integer",
                "description": "Teeth on large sprocket. Must be >= z_small.",
            },
            "chain_no": {
                "type": "string",
                "enum": [
                    "25", "35", "40", "50", "60", "80",
                    "100", "120", "140", "160", "180", "200", "240",
                ],
                "description": (
                    "ANSI chain number. If omitted, smallest adequate chain "
                    "is selected automatically."
                ),
            },
            "load_type": {
                "type": "string",
                "enum": ["smooth", "moderate", "heavy"],
                "description": (
                    "Load character: 'smooth' (Ks=1.0, default), "
                    "'moderate' (Ks=1.25), 'heavy' (Ks=1.5)."
                ),
            },
            "n_strands": {
                "type": "integer",
                "description": "Number of parallel strands. Default 1. Must be >= 1.",
            },
        },
        "required": ["power_kW", "n_small_rpm", "z_small", "z_large"],
    },
)


@register(_chain_drive_design_spec, write=False)
async def run_chain_drive_design(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("power_kW", "n_small_rpm", "z_small", "z_large"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("chain_no", "load_type", "n_strands"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = chain_drive_design(
        a["power_kW"], a["n_small_rpm"], a["z_small"], a["z_large"], **kwargs
    )
    return ok_payload(result)
