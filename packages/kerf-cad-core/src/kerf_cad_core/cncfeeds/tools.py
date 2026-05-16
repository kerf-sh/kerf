"""
kerf_cad_core.cncfeeds.tools — LLM tool wrappers for machining feeds & speeds.

Registers thirteen tools with the Kerf tool registry:

  cnc_spindle_rpm           — spindle RPM from cutting speed & diameter
  cnc_feed_rate             — table feed rate from chip load × teeth × RPM
  cnc_mrr_milling           — material-removal rate for milling
  cnc_mrr_drilling          — material-removal rate for drilling
  cnc_mrr_turning           — material-removal rate for turning
  cnc_cutting_power         — cutting power & torque from Kc
  cnc_tangential_force      — tangential cutting force from Kc
  cnc_chip_thinning         — chip-thinning correction factor
  cnc_corrected_chip_load   — chip load adjusted for chip thinning
  cnc_tool_deflection       — cantilever tool deflection & max stickout
  cnc_surface_finish_ra     — theoretical Ra from feed & nose radius
  cnc_drill_thrust_torque   — drilling thrust & torque
  cnc_tapping_speed         — axial feed for rigid tapping

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
Machinery's Handbook, 30th ed.
Sandvik Coromant Machining Handbooks (Milling, Turning, Drilling)
Kennametal Machining Data Handbook

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.cncfeeds.calc import (
    MATERIAL_KC,
    chip_thinning_factor,
    corrected_chip_load,
    cutting_power,
    drill_thrust_torque,
    feed_rate,
    mrr_drilling,
    mrr_milling,
    mrr_turning,
    spindle_rpm,
    surface_finish_ra,
    tangential_force,
    tapping_speed,
    tool_deflection,
)

_MATERIAL_KC_KEYS = sorted(MATERIAL_KC.keys())
_MATERIAL_ENUM_DESC = "; ".join(f"{k}: {v:.0f}" for k, v in sorted(MATERIAL_KC.items()))


# ---------------------------------------------------------------------------
# Tool: cnc_spindle_rpm
# ---------------------------------------------------------------------------

_spindle_rpm_spec = ToolSpec(
    name="cnc_spindle_rpm",
    description=(
        "Compute spindle speed (RPM) from cutting speed and cutter or workpiece "
        "diameter.\n"
        "\n"
        "Formula: n = 1000 × vc / (π × D)\n"
        "\n"
        "Returns rpm.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "vc": {
                "type": "number",
                "description": "Cutting speed (m/min). Must be > 0.",
            },
            "diameter": {
                "type": "number",
                "description": "Cutter or workpiece diameter (mm). Must be > 0.",
            },
        },
        "required": ["vc", "diameter"],
    },
)


@register(_spindle_rpm_spec, write=False)
async def run_spindle_rpm(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("vc") is None:
        return json.dumps({"ok": False, "reason": "vc is required"})
    if a.get("diameter") is None:
        return json.dumps({"ok": False, "reason": "diameter is required"})

    result = spindle_rpm(a["vc"], a["diameter"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: cnc_feed_rate
# ---------------------------------------------------------------------------

_feed_rate_spec = ToolSpec(
    name="cnc_feed_rate",
    description=(
        "Compute table feed rate (mm/min) from chip load, number of teeth, and "
        "spindle speed.\n"
        "\n"
        "Formula: Vf = fz × z × n\n"
        "\n"
        "Returns feed_mm_min.  Flags chip_load_low / chip_load_high in warnings.  "
        "Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "chip_load": {
                "type": "number",
                "description": "Chip load per tooth fz (mm/tooth). Must be > 0.",
            },
            "teeth": {
                "type": "integer",
                "description": "Number of cutter teeth / flutes. Must be >= 1.",
            },
            "rpm": {
                "type": "number",
                "description": "Spindle speed (rev/min). Must be > 0.",
            },
        },
        "required": ["chip_load", "teeth", "rpm"],
    },
)


@register(_feed_rate_spec, write=False)
async def run_feed_rate(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("chip_load", "teeth", "rpm"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = feed_rate(a["chip_load"], a["teeth"], a["rpm"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: cnc_mrr_milling
# ---------------------------------------------------------------------------

_mrr_milling_spec = ToolSpec(
    name="cnc_mrr_milling",
    description=(
        "Compute material-removal rate (MRR) for milling operations.\n"
        "\n"
        "Formula: Q = ae × ap × Vf   [mm³/min]\n"
        "\n"
        "Returns mrr_mm3_min.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "width": {
                "type": "number",
                "description": "Radial engagement / width of cut ae (mm). Must be > 0.",
            },
            "depth": {
                "type": "number",
                "description": "Axial depth of cut ap (mm). Must be > 0.",
            },
            "feed_mm_min": {
                "type": "number",
                "description": "Table feed rate Vf (mm/min). Must be > 0.",
            },
        },
        "required": ["width", "depth", "feed_mm_min"],
    },
)


@register(_mrr_milling_spec, write=False)
async def run_mrr_milling(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("width", "depth", "feed_mm_min"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = mrr_milling(a["width"], a["depth"], a["feed_mm_min"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: cnc_mrr_drilling
# ---------------------------------------------------------------------------

_mrr_drilling_spec = ToolSpec(
    name="cnc_mrr_drilling",
    description=(
        "Compute material-removal rate (MRR) for drilling.\n"
        "\n"
        "Formula: Q = (π/4) × D² × fn × n   [mm³/min]\n"
        "\n"
        "Returns mrr_mm3_min and feed_mm_min.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "diameter": {
                "type": "number",
                "description": "Drill diameter D (mm). Must be > 0.",
            },
            "feed_per_rev": {
                "type": "number",
                "description": "Feed per revolution fn (mm/rev). Must be > 0.",
            },
            "rpm": {
                "type": "number",
                "description": "Spindle speed (rev/min). Must be > 0.",
            },
        },
        "required": ["diameter", "feed_per_rev", "rpm"],
    },
)


@register(_mrr_drilling_spec, write=False)
async def run_mrr_drilling(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("diameter", "feed_per_rev", "rpm"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = mrr_drilling(a["diameter"], a["feed_per_rev"], a["rpm"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: cnc_mrr_turning
# ---------------------------------------------------------------------------

_mrr_turning_spec = ToolSpec(
    name="cnc_mrr_turning",
    description=(
        "Compute material-removal rate (MRR) for turning (external or internal).\n"
        "\n"
        "Formula: Q = ap × fn × vc × 1000   [mm³/min]\n"
        "\n"
        "Returns mrr_mm3_min.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "depth_of_cut": {
                "type": "number",
                "description": "Radial depth of cut ap (mm). Must be > 0.",
            },
            "feed_per_rev": {
                "type": "number",
                "description": "Feed per revolution fn (mm/rev). Must be > 0.",
            },
            "vc": {
                "type": "number",
                "description": "Cutting speed vc (m/min). Must be > 0.",
            },
        },
        "required": ["depth_of_cut", "feed_per_rev", "vc"],
    },
)


@register(_mrr_turning_spec, write=False)
async def run_mrr_turning(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("depth_of_cut", "feed_per_rev", "vc"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = mrr_turning(a["depth_of_cut"], a["feed_per_rev"], a["vc"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: cnc_cutting_power
# ---------------------------------------------------------------------------

_cutting_power_spec = ToolSpec(
    name="cnc_cutting_power",
    description=(
        "Compute cutting power (W) and spindle torque (N·m) from MRR and "
        "specific cutting energy Kc.\n"
        "\n"
        "Formula: Pc = kc × Q / 60000   [W]; Ps = Pc / η\n"
        "\n"
        f"Material Kc reference values (N/mm²): {_MATERIAL_ENUM_DESC}.\n"
        "\n"
        "Flags over_power if spindle_power_W exceeds machine_power_W.  "
        "Returns cutting_power_W, spindle_power_W, and optionally torque_Nm.  "
        "Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "mrr": {
                "type": "number",
                "description": "Material-removal rate Q (mm³/min). Must be > 0.",
            },
            "kc": {
                "type": "number",
                "description": (
                    "Specific cutting energy (N/mm²). Must be > 0. "
                    "Use MATERIAL_KC table as reference."
                ),
            },
            "efficiency": {
                "type": "number",
                "description": "Spindle mechanical efficiency η (default 0.85). Range (0, 1].",
            },
            "machine_power_W": {
                "type": "number",
                "description": "Machine spindle rated power (W, default 7500). Used for over_power warning.",
            },
            "rpm": {
                "type": "number",
                "description": "Spindle speed (rev/min). Optional — required for torque calculation.",
            },
            "diameter_mm": {
                "type": "number",
                "description": "Cutter diameter (mm). Optional — required for torque calculation.",
            },
        },
        "required": ["mrr", "kc"],
    },
)


@register(_cutting_power_spec, write=False)
async def run_cutting_power(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("mrr") is None:
        return json.dumps({"ok": False, "reason": "mrr is required"})
    if a.get("kc") is None:
        return json.dumps({"ok": False, "reason": "kc is required"})

    kwargs: dict = {}
    for opt in ("efficiency", "machine_power_W", "rpm", "diameter_mm"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = cutting_power(a["mrr"], a["kc"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: cnc_tangential_force
# ---------------------------------------------------------------------------

_tangential_force_spec = ToolSpec(
    name="cnc_tangential_force",
    description=(
        "Compute tangential (main) cutting force Ft from specific cutting energy.\n"
        "\n"
        "Formula: Ft = kc × fz × ap × ae   [N]\n"
        "\n"
        "Returns tangential_N.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "kc": {
                "type": "number",
                "description": "Specific cutting energy (N/mm²). Must be > 0.",
            },
            "chip_load": {
                "type": "number",
                "description": "Chip load fz (mm/tooth). Must be > 0.",
            },
            "depth_of_cut": {
                "type": "number",
                "description": "Axial depth of cut ap (mm). Must be > 0.",
            },
            "width_of_cut": {
                "type": "number",
                "description": "Width of cut / radial engagement ae (mm, default 1.0). Must be > 0.",
            },
        },
        "required": ["kc", "chip_load", "depth_of_cut"],
    },
)


@register(_tangential_force_spec, write=False)
async def run_tangential_force(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("kc", "chip_load", "depth_of_cut"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "width_of_cut" in a:
        kwargs["width_of_cut"] = a["width_of_cut"]

    result = tangential_force(a["kc"], a["chip_load"], a["depth_of_cut"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: cnc_chip_thinning
# ---------------------------------------------------------------------------

_chip_thinning_spec = ToolSpec(
    name="cnc_chip_thinning",
    description=(
        "Compute the chip-thinning factor (CTF) for radial engagement < 50%.\n"
        "\n"
        "When ae < D/2, actual chip thickness < programmed chip load.\n"
        "Formula: CTF = D / (2 × √(ae × (D − ae)))   when ae < D/2;\n"
        "         CTF = 1.0 otherwise.\n"
        "\n"
        "Flags chip_thinning_severe if ae/D < 0.05.  Returns ctf and ae_over_D.  "
        "Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "radial_engagement": {
                "type": "number",
                "description": "Radial engagement ae (mm). Must be > 0 and <= diameter.",
            },
            "diameter": {
                "type": "number",
                "description": "Cutter diameter D (mm). Must be > 0.",
            },
        },
        "required": ["radial_engagement", "diameter"],
    },
)


@register(_chip_thinning_spec, write=False)
async def run_chip_thinning(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("radial_engagement") is None:
        return json.dumps({"ok": False, "reason": "radial_engagement is required"})
    if a.get("diameter") is None:
        return json.dumps({"ok": False, "reason": "diameter is required"})

    result = chip_thinning_factor(a["radial_engagement"], a["diameter"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: cnc_corrected_chip_load
# ---------------------------------------------------------------------------

_corrected_chip_load_spec = ToolSpec(
    name="cnc_corrected_chip_load",
    description=(
        "Compute the programmed chip load that accounts for chip thinning.\n"
        "\n"
        "programmed_chip_load = target_chip_load × CTF\n"
        "\n"
        "Returns programmed_chip_load_mm and ctf.  "
        "Flags chip_load_low / chip_load_high / chip_thinning_severe.  "
        "Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "nominal_chip_load": {
                "type": "number",
                "description": "Target actual chip thickness (mm/tooth). Must be > 0.",
            },
            "ae": {
                "type": "number",
                "description": "Radial engagement ae (mm). Must be > 0 and <= diameter.",
            },
            "diameter": {
                "type": "number",
                "description": "Cutter diameter (mm). Must be > 0.",
            },
        },
        "required": ["nominal_chip_load", "ae", "diameter"],
    },
)


@register(_corrected_chip_load_spec, write=False)
async def run_corrected_chip_load(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("nominal_chip_load", "ae", "diameter"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = corrected_chip_load(a["nominal_chip_load"], a["ae"], a["diameter"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: cnc_tool_deflection
# ---------------------------------------------------------------------------

_tool_deflection_spec = ToolSpec(
    name="cnc_tool_deflection",
    description=(
        "Compute cantilever tool deflection and maximum safe stickout.\n"
        "\n"
        "Models tool shank as cantilever beam: δ = F × L³ / (3 × EI)\n"
        "\n"
        "Returns deflection_mm and max_stickout_mm.  "
        "Flags excessive_deflection if δ > 0.025 mm or stickout > 4× diameter.  "
        "Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "force": {
                "type": "number",
                "description": "Transverse cutting force at tool tip (N). Must be > 0.",
            },
            "overhang": {
                "type": "number",
                "description": "Tool stickout from spindle face (mm). Must be > 0.",
            },
            "diameter": {
                "type": "number",
                "description": "Shank diameter (mm). Must be > 0.",
            },
            "E_GPa": {
                "type": "number",
                "description": (
                    "Young's modulus of shank material (GPa, default 600 for solid carbide). "
                    "Steel/HSS ≈ 210 GPa."
                ),
            },
        },
        "required": ["force", "overhang", "diameter"],
    },
)


@register(_tool_deflection_spec, write=False)
async def run_tool_deflection(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("force", "overhang", "diameter"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "E_GPa" in a:
        kwargs["E_GPa"] = a["E_GPa"]

    result = tool_deflection(a["force"], a["overhang"], a["diameter"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: cnc_surface_finish_ra
# ---------------------------------------------------------------------------

_surface_finish_ra_spec = ToolSpec(
    name="cnc_surface_finish_ra",
    description=(
        "Estimate theoretical surface roughness Ra from feed per revolution "
        "and tool nose radius.\n"
        "\n"
        "Formula (Machinery's Handbook): Ra ≈ fn² / (32 × r_ε)   [mm → µm]\n"
        "\n"
        "Returns Ra_um and Rz_um.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "feed_per_rev": {
                "type": "number",
                "description": "Feed per revolution fn (mm/rev). Must be > 0.",
            },
            "nose_radius": {
                "type": "number",
                "description": "Tool nose radius r_ε (mm). Must be > 0.",
            },
        },
        "required": ["feed_per_rev", "nose_radius"],
    },
)


@register(_surface_finish_ra_spec, write=False)
async def run_surface_finish_ra(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("feed_per_rev") is None:
        return json.dumps({"ok": False, "reason": "feed_per_rev is required"})
    if a.get("nose_radius") is None:
        return json.dumps({"ok": False, "reason": "nose_radius is required"})

    result = surface_finish_ra(a["feed_per_rev"], a["nose_radius"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: cnc_drill_thrust_torque
# ---------------------------------------------------------------------------

_drill_thrust_torque_spec = ToolSpec(
    name="cnc_drill_thrust_torque",
    description=(
        "Compute drilling thrust force (N) and torque (N·m) from cutting parameters.\n"
        "\n"
        "Formulas (Sandvik / Machinery's Handbook):\n"
        "  Thrust: Ff = kc × fn × (D/2) × sin(κ)       [N]\n"
        "  Torque: Mc = kc × fn × D² / 8 / 1000         [N·m]\n"
        "  where κ = drill_point_angle / 2.\n"
        "\n"
        "Returns thrust_N and torque_Nm.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "diameter": {
                "type": "number",
                "description": "Drill diameter D (mm). Must be > 0.",
            },
            "feed_per_rev": {
                "type": "number",
                "description": "Feed per revolution fn (mm/rev). Must be > 0.",
            },
            "kc": {
                "type": "number",
                "description": "Specific cutting energy (N/mm²). Must be > 0.",
            },
            "drill_point_angle": {
                "type": "number",
                "description": "Included drill point angle (degrees, default 118°). Range (0, 180).",
            },
        },
        "required": ["diameter", "feed_per_rev", "kc"],
    },
)


@register(_drill_thrust_torque_spec, write=False)
async def run_drill_thrust_torque(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("diameter", "feed_per_rev", "kc"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "drill_point_angle" in a:
        kwargs["drill_point_angle"] = a["drill_point_angle"]

    result = drill_thrust_torque(a["diameter"], a["feed_per_rev"], a["kc"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: cnc_tapping_speed
# ---------------------------------------------------------------------------

_tapping_speed_spec = ToolSpec(
    name="cnc_tapping_speed",
    description=(
        "Compute the required axial feed rate for rigid (synchronised) tapping.\n"
        "\n"
        "Formula: Vf = p × n   [mm/min]\n"
        "\n"
        "The CNC controller must synchronise spindle rotation to this feed to "
        "cut the correct thread pitch.  Returns feed_mm_min.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "pitch": {
                "type": "number",
                "description": (
                    "Thread pitch p (mm/rev). Must be > 0. "
                    "Metric: pitch in mm (e.g. M8×1.25 → 1.25). "
                    "Unified (UNC/UNF): 25.4 / TPI."
                ),
            },
            "rpm": {
                "type": "number",
                "description": "Spindle speed (rev/min). Must be > 0.",
            },
        },
        "required": ["pitch", "rpm"],
    },
)


@register(_tapping_speed_spec, write=False)
async def run_tapping_speed(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("pitch") is None:
        return json.dumps({"ok": False, "reason": "pitch is required"})
    if a.get("rpm") is None:
        return json.dumps({"ok": False, "reason": "rpm is required"})

    result = tapping_speed(a["pitch"], a["rpm"])
    return ok_payload(result)
