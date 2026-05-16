"""
kerf_cad_core.clutchbrake.tools — LLM tool wrappers for clutch & brake design.

Registers tools with the Kerf tool registry:

  disc_clutch_torque    — disc/plate clutch torque (uniform-wear / uniform-pressure)
  cone_clutch_torque    — cone clutch torque & actuation force
  band_brake_torque     — flexible band brake (capstan equation)
  drum_brake_torque     — long-shoe drum brake (leading / trailing shoe)
  disc_brake_torque     — caliper disc brake torque
  engagement_energy     — energy dissipated during engagement
  temperature_rise      — lumped temperature rise per engagement
  heat_dissipation_area — minimum cooling area for steady power
  wear_pv_check         — pV limit check vs. friction material catalog
  engagement_time       — synchronisation time + slip energy
  friction_material_props — look up μ, max_pV, max_temp for a material

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
Shigley's Mechanical Engineering Design, 10th ed., §§ 16-1 to 16-12
Juvinall & Marshek, Machine Component Design, 5th ed., §§ 18.1-18.9

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.clutchbrake.design import (
    disc_clutch_torque,
    cone_clutch_torque,
    band_brake_torque,
    drum_brake_torque,
    disc_brake_torque,
    engagement_energy,
    temperature_rise,
    heat_dissipation_area,
    wear_pv_check,
    engagement_time,
    friction_material_props,
)


# ---------------------------------------------------------------------------
# Tool: disc_clutch_torque
# ---------------------------------------------------------------------------

_disc_clutch_spec = ToolSpec(
    name="disc_clutch_torque",
    description=(
        "Compute the torque capacity of a disc / plate clutch.\n"
        "\n"
        "Supports uniform-wear (Shigley §16-2, preferred for design) and "
        "uniform-pressure (new or relapped surfaces) theories. "
        "Multi-plate configurations are handled via n_plates.\n"
        "\n"
        "Returns torque_Nm (total), torque per friction surface, effective "
        "friction radius, and actuation force relationship.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "F_a": {
                "type": "number",
                "description": "Axial actuation force (N). Must be > 0.",
            },
            "mu": {
                "type": "number",
                "description": "Coefficient of friction (dimensionless). Must be > 0.",
            },
            "r_o": {
                "type": "number",
                "description": "Outer friction radius (m). Must be > r_i.",
            },
            "r_i": {
                "type": "number",
                "description": "Inner friction radius (m). Must be >= 0.",
            },
            "method": {
                "type": "string",
                "enum": ["uniform-wear", "uniform-pressure"],
                "description": (
                    "Pressure distribution theory: 'uniform-wear' (default, "
                    "conservative) or 'uniform-pressure' (new surfaces)."
                ),
            },
            "n_plates": {
                "type": "integer",
                "description": (
                    "Number of friction disc pairs (default 1). "
                    "Each pair contributes 2 friction surfaces."
                ),
            },
        },
        "required": ["F_a", "mu", "r_o", "r_i"],
    },
)


@register(_disc_clutch_spec, write=False)
async def run_disc_clutch_torque(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("F_a", "mu", "r_o", "r_i"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "method" in a:
        kwargs["method"] = a["method"]
    if "n_plates" in a:
        kwargs["n_plates"] = a["n_plates"]

    result = disc_clutch_torque(a["F_a"], a["mu"], a["r_o"], a["r_i"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: cone_clutch_torque
# ---------------------------------------------------------------------------

_cone_clutch_spec = ToolSpec(
    name="cone_clutch_torque",
    description=(
        "Compute the torque capacity and actuation force of a cone clutch.\n"
        "\n"
        "The cone half-angle α is from the rotation axis to the cone surface "
        "(typically 8°–15°). Below ~6° the clutch may self-lock.\n"
        "\n"
        "Returns torque_Nm, actuation force, effective friction radius, "
        "sin(α), and self_lock flag.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "F_a": {
                "type": "number",
                "description": "Axial engagement force (N). Must be > 0.",
            },
            "mu": {
                "type": "number",
                "description": "Coefficient of friction. Must be > 0.",
            },
            "r_o": {
                "type": "number",
                "description": "Outer cone radius (m). Must be > r_i.",
            },
            "r_i": {
                "type": "number",
                "description": "Inner cone radius (m). Must be >= 0.",
            },
            "half_angle_deg": {
                "type": "number",
                "description": "Cone half-angle α (degrees). Must be > 0. Typical: 8–15°.",
            },
            "method": {
                "type": "string",
                "enum": ["uniform-wear", "uniform-pressure"],
                "description": (
                    "Pressure distribution: 'uniform-wear' (default) or 'uniform-pressure'."
                ),
            },
        },
        "required": ["F_a", "mu", "r_o", "r_i", "half_angle_deg"],
    },
)


@register(_cone_clutch_spec, write=False)
async def run_cone_clutch_torque(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("F_a", "mu", "r_o", "r_i", "half_angle_deg"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "method" in a:
        kwargs["method"] = a["method"]

    result = cone_clutch_torque(
        a["F_a"], a["mu"], a["r_o"], a["r_i"], a["half_angle_deg"], **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: band_brake_torque
# ---------------------------------------------------------------------------

_band_brake_spec = ToolSpec(
    name="band_brake_torque",
    description=(
        "Compute band brake braking torque using the capstan equation.\n"
        "\n"
        "F_tight / F_slack = exp(μ·θ)\n"
        "T = (F_tight - F_slack) × r\n"
        "\n"
        "Returns torque_Nm, tight/slack forces, capstan ratio, and "
        "self-energizing factor exp(μ·θ).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "drum_radius": {
                "type": "number",
                "description": "Drum radius r (m). Must be > 0.",
            },
            "angle_wrap_deg": {
                "type": "number",
                "description": "Band wrap angle θ (degrees). Must be > 0.",
            },
            "mu": {
                "type": "number",
                "description": "Band-drum coefficient of friction. Must be > 0.",
            },
            "F_tight": {
                "type": "number",
                "description": "Tight-side band tension (N). Must be > 0.",
            },
            "self_energizing": {
                "type": "boolean",
                "description": (
                    "If true, report the self-energizing factor "
                    "exp(μ·θ). Default false."
                ),
            },
        },
        "required": ["drum_radius", "angle_wrap_deg", "mu", "F_tight"],
    },
)


@register(_band_brake_spec, write=False)
async def run_band_brake_torque(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("drum_radius", "angle_wrap_deg", "mu", "F_tight"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "self_energizing" in a:
        kwargs["self_energizing"] = a["self_energizing"]

    result = band_brake_torque(
        a["drum_radius"], a["angle_wrap_deg"], a["mu"], a["F_tight"], **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: drum_brake_torque
# ---------------------------------------------------------------------------

_drum_brake_spec = ToolSpec(
    name="drum_brake_torque",
    description=(
        "Compute drum brake torque using the Shigley long-shoe formulation.\n"
        "\n"
        "Handles leading (self-energizing) and trailing (self-dragging) shoes. "
        "A self-locking warning is issued when the leading shoe geometry causes "
        "M_f >= M_n.\n"
        "\n"
        "Returns torque_Nm, required actuating force, M_n, M_f, and "
        "self_energizing flag.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "drum_radius": {
                "type": "number",
                "description": "Drum radius r (m). Must be > 0.",
            },
            "shoe_width": {
                "type": "number",
                "description": "Shoe face width b (m). Must be > 0.",
            },
            "mu": {
                "type": "number",
                "description": "Coefficient of friction. Must be > 0.",
            },
            "p_max": {
                "type": "number",
                "description": "Maximum contact pressure on shoe (Pa). Must be > 0.",
            },
            "theta1_deg": {
                "type": "number",
                "description": "Shoe leading-edge angle from pivot (degrees). Typically 0–30°.",
            },
            "theta2_deg": {
                "type": "number",
                "description": "Shoe trailing-edge angle from pivot (degrees). Must be > theta1_deg.",
            },
            "pivot_a": {
                "type": "number",
                "description": "Distance from drum centre to shoe pivot (m). Must be > 0.",
            },
            "shoe_type": {
                "type": "string",
                "enum": ["leading", "trailing"],
                "description": (
                    "'leading' (default, self-energizing) or 'trailing' (self-dragging)."
                ),
            },
        },
        "required": [
            "drum_radius", "shoe_width", "mu", "p_max",
            "theta1_deg", "theta2_deg", "pivot_a",
        ],
    },
)


@register(_drum_brake_spec, write=False)
async def run_drum_brake_torque(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("drum_radius", "shoe_width", "mu", "p_max",
                  "theta1_deg", "theta2_deg", "pivot_a"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "shoe_type" in a:
        kwargs["shoe_type"] = a["shoe_type"]

    result = drum_brake_torque(
        a["drum_radius"], a["shoe_width"], a["mu"], a["p_max"],
        a["theta1_deg"], a["theta2_deg"], a["pivot_a"],
        **kwargs,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: disc_brake_torque
# ---------------------------------------------------------------------------

_disc_brake_spec = ToolSpec(
    name="disc_brake_torque",
    description=(
        "Compute caliper disc brake braking torque.\n"
        "\n"
        "T = n_pads × μ × F_clamp × r_eff\n"
        "\n"
        "Returns torque_Nm for the specified number of pads.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "F_clamp": {
                "type": "number",
                "description": "Clamping force per pad (N). Must be > 0.",
            },
            "mu": {
                "type": "number",
                "description": "Pad-rotor coefficient of friction. Must be > 0.",
            },
            "r_eff": {
                "type": "number",
                "description": "Effective friction radius — typically mid-pad radius (m). Must be > 0.",
            },
            "n_pads": {
                "type": "integer",
                "description": (
                    "Number of friction pads (default 2 for floating caliper, "
                    "4 for fixed caliper)."
                ),
            },
        },
        "required": ["F_clamp", "mu", "r_eff"],
    },
)


@register(_disc_brake_spec, write=False)
async def run_disc_brake_torque(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("F_clamp", "mu", "r_eff"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "n_pads" in a:
        kwargs["n_pads"] = a["n_pads"]

    result = disc_brake_torque(a["F_clamp"], a["mu"], a["r_eff"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: engagement_energy
# ---------------------------------------------------------------------------

_engagement_energy_spec = ToolSpec(
    name="engagement_energy",
    description=(
        "Compute energy dissipated during a clutch / brake engagement.\n"
        "\n"
        "Two components:\n"
        "  1. Kinetic energy from inertia redistribution:  ½·I_eff·Δω²\n"
        "  2. Work done against load during slip (optional).\n"
        "\n"
        "Returns E_slip_J (total), E_kinetic_J, E_load_J, Δω, I_eff.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "omega1_rad_s": {
                "type": "number",
                "description": "Driving shaft angular velocity (rad/s). Must be >= 0.",
            },
            "omega2_rad_s": {
                "type": "number",
                "description": "Driven shaft initial angular velocity (rad/s). Must be >= 0.",
            },
            "I_driving": {
                "type": "number",
                "description": "Driving-side mass moment of inertia (kg·m²). Must be > 0.",
            },
            "I_driven": {
                "type": "number",
                "description": "Driven-side mass moment of inertia (kg·m²). Must be > 0.",
            },
            "T_load_Nm": {
                "type": "number",
                "description": "Resisting load torque on driven side (N·m, default 0).",
            },
            "t_engage_s": {
                "type": "number",
                "description": (
                    "Engagement/slip time (s). If provided, load work is added to "
                    "slip energy. Must be > 0 if given."
                ),
            },
        },
        "required": ["omega1_rad_s", "omega2_rad_s", "I_driving", "I_driven"],
    },
)


@register(_engagement_energy_spec, write=False)
async def run_engagement_energy(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("omega1_rad_s", "omega2_rad_s", "I_driving", "I_driven"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "T_load_Nm" in a:
        kwargs["T_load_Nm"] = a["T_load_Nm"]
    if "t_engage_s" in a:
        kwargs["t_engage_s"] = a["t_engage_s"]

    result = engagement_energy(
        a["omega1_rad_s"], a["omega2_rad_s"], a["I_driving"], a["I_driven"],
        **kwargs,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: temperature_rise
# ---------------------------------------------------------------------------

_temperature_rise_spec = ToolSpec(
    name="clutch_temperature_rise",
    description=(
        "Estimate the lumped temperature rise of the rotor/drum from one "
        "clutch or brake engagement.\n"
        "\n"
        "ΔT = (fraction × E_slip) / (m × cp)\n"
        "\n"
        "Returns delta_T_K (°C increment). Input E_slip_J from "
        "engagement_energy.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "E_slip_J": {
                "type": "number",
                "description": "Slip energy dissipated (J). Must be > 0.",
            },
            "mass_rotor_kg": {
                "type": "number",
                "description": "Effective thermal mass of rotor/drum (kg). Must be > 0.",
            },
            "cp_J_per_kgK": {
                "type": "number",
                "description": (
                    "Specific heat (J/kg·K). Default 500 (steel/cast iron). Must be > 0."
                ),
            },
            "fraction_to_rotor": {
                "type": "number",
                "description": (
                    "Fraction of slip energy going to the rotor (0–1). Default 0.5."
                ),
            },
        },
        "required": ["E_slip_J", "mass_rotor_kg"],
    },
)


@register(_temperature_rise_spec, write=False)
async def run_temperature_rise(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("E_slip_J", "mass_rotor_kg"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "cp_J_per_kgK" in a:
        kwargs["cp_J_per_kgK"] = a["cp_J_per_kgK"]
    if "fraction_to_rotor" in a:
        kwargs["fraction_to_rotor"] = a["fraction_to_rotor"]

    result = temperature_rise(a["E_slip_J"], a["mass_rotor_kg"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: heat_dissipation_area
# ---------------------------------------------------------------------------

_heat_dissipation_area_spec = ToolSpec(
    name="clutch_heat_dissipation_area",
    description=(
        "Compute the minimum heat-dissipation area for steady-state convective "
        "cooling of a clutch or brake.\n"
        "\n"
        "A = Q / (h × ΔT)\n"
        "\n"
        "Returns area_m2 (m²).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "power_W": {
                "type": "number",
                "description": "Heat dissipation power (W). Must be > 0.",
            },
            "h_conv": {
                "type": "number",
                "description": (
                    "Convective heat-transfer coefficient (W/m²·K). "
                    "Default 20 (natural convection in air). Must be > 0."
                ),
            },
            "delta_T_K": {
                "type": "number",
                "description": (
                    "Allowable surface-to-ambient temperature difference (K). "
                    "Default 80 K. Must be > 0."
                ),
            },
        },
        "required": ["power_W"],
    },
)


@register(_heat_dissipation_area_spec, write=False)
async def run_heat_dissipation_area(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("power_W") is None:
        return json.dumps({"ok": False, "reason": "power_W is required"})

    kwargs: dict = {}
    if "h_conv" in a:
        kwargs["h_conv"] = a["h_conv"]
    if "delta_T_K" in a:
        kwargs["delta_T_K"] = a["delta_T_K"]

    result = heat_dissipation_area(a["power_W"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: wear_pv_check
# ---------------------------------------------------------------------------

_wear_pv_spec = ToolSpec(
    name="clutch_wear_pv_check",
    description=(
        "Check whether the contact pressure × slip velocity (pV) product is "
        "within the friction material's allowable limit.\n"
        "\n"
        "Returns pv_Pa_m_s, pv_max, pv_ok, safety_factor, and warnings if "
        "the limit is exceeded.\n"
        "\n"
        "Available materials include: cast_iron_dry, cast_iron_wet, "
        "molded_dry, molded_wet, sintered_metal_dry, paper_wet, carbon_graphite, "
        "asbestos_dry, asbestos_wet, bronze_dry, steel_dry, cork_dry, wood_dry.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "p_contact": {
                "type": "number",
                "description": "Average contact pressure on friction surface (Pa). Must be > 0.",
            },
            "v_slip": {
                "type": "number",
                "description": "Average sliding / slip velocity at friction surface (m/s). Must be > 0.",
            },
            "material": {
                "type": "string",
                "description": (
                    "Friction material name from built-in catalog "
                    "(e.g. 'cast_iron_dry', 'molded_dry', 'sintered_metal_dry')."
                ),
            },
        },
        "required": ["p_contact", "v_slip", "material"],
    },
)


@register(_wear_pv_spec, write=False)
async def run_wear_pv_check(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("p_contact", "v_slip", "material"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = wear_pv_check(a["p_contact"], a["v_slip"], a["material"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: engagement_time
# ---------------------------------------------------------------------------

_engagement_time_spec = ToolSpec(
    name="engagement_time",
    description=(
        "Compute the synchronisation time and slip energy during a clutch "
        "engagement assuming constant transmitted torque.\n"
        "\n"
        "t_sync = Δω × I₁ × I₂ / [(T_c - T_load) × (I₁ + I₂)]\n"
        "\n"
        "Returns t_sync_s, E_slip_J, omega_sync, t_sync_feasible.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "omega1_rad_s": {
                "type": "number",
                "description": "Driving shaft initial angular velocity (rad/s). Must be >= 0.",
            },
            "omega2_rad_s": {
                "type": "number",
                "description": "Driven shaft initial angular velocity (rad/s). Must be >= 0.",
            },
            "I_driving": {
                "type": "number",
                "description": "Driving-side inertia (kg·m²). Must be > 0.",
            },
            "I_driven": {
                "type": "number",
                "description": "Driven-side inertia (kg·m²). Must be > 0.",
            },
            "T_clutch_Nm": {
                "type": "number",
                "description": "Clutch (transmitted) torque during slip (N·m). Must be > 0.",
            },
            "T_load_Nm": {
                "type": "number",
                "description": "Load torque on driven side (N·m, default 0).",
            },
        },
        "required": [
            "omega1_rad_s", "omega2_rad_s", "I_driving", "I_driven", "T_clutch_Nm",
        ],
    },
)


@register(_engagement_time_spec, write=False)
async def run_engagement_time(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("omega1_rad_s", "omega2_rad_s", "I_driving", "I_driven", "T_clutch_Nm"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "T_load_Nm" in a:
        kwargs["T_load_Nm"] = a["T_load_Nm"]

    result = engagement_time(
        a["omega1_rad_s"], a["omega2_rad_s"],
        a["I_driving"], a["I_driven"], a["T_clutch_Nm"],
        **kwargs,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: friction_material_props
# ---------------------------------------------------------------------------

_friction_material_spec = ToolSpec(
    name="friction_material_props",
    description=(
        "Look up friction material properties from the built-in catalog.\n"
        "\n"
        "Returns μ (dry coefficient of friction), max_pV (Pa·m/s), and "
        "max_temp (°C) for the specified material.\n"
        "\n"
        "Available materials: cast_iron_dry, cast_iron_wet, steel_dry, "
        "bronze_dry, asbestos_dry, asbestos_wet, molded_dry, molded_wet, "
        "paper_wet, sintered_metal_dry, cork_dry, wood_dry, carbon_graphite.\n"
        "\n"
        "Errors: {ok:false, reason} for unknown material. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "material": {
                "type": "string",
                "description": (
                    "Friction material name from the built-in catalog "
                    "(e.g. 'cast_iron_dry', 'molded_dry', 'sintered_metal_dry')."
                ),
            },
        },
        "required": ["material"],
    },
)


@register(_friction_material_spec, write=False)
async def run_friction_material_props(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("material") is None:
        return json.dumps({"ok": False, "reason": "material is required"})

    result = friction_material_props(a["material"])
    return ok_payload(result)
