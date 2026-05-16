"""
kerf_cad_core.mooring.tools — LLM tool wrappers for offshore mooring & station-keeping.

Registers the following tools with the Kerf tool registry:

  mooring_catenary_line       — single-segment elastic catenary line analysis
  mooring_multiseg_catenary   — multi-segment (chain+wire) catenary analysis
  mooring_system_stiffness    — restoring force vs offset & system stiffness
  mooring_anchor_holding      — drag-embedment / pile / suction-caisson capacity
  mooring_morison_force       — Morison wave + current force on a cylinder
  mooring_mean_env_load       — mean wind + current hull drag (OCIMF-style)
  mooring_watch_circle        — watch circle & API RP 2SK max offset check
  mooring_line_sf             — line tension safety factor (API RP 2SK)
  mooring_riser_top_tension   — riser top tension (API RP 16Q / DNV-OS-F201)

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
API RP 2SK (3rd ed., 2005) — Design and Analysis of Station-Keeping Systems.
DNV-OS-E301 — Position Mooring.
Morison, J.R. et al. (1950) — "The Force Exerted by Surface Waves on Piles".
OCIMF MEG3 — Mooring Equipment Guidelines.

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.mooring.lines import (
    catenary_line,
    multiseg_catenary,
    mooring_system,
    anchor_holding,
    morison_wave_current,
    mean_env_load,
    watch_circle,
    line_safety_factor,
    riser_top_tension,
)


# ---------------------------------------------------------------------------
# Tool: mooring_catenary_line
# ---------------------------------------------------------------------------

_catenary_line_spec = ToolSpec(
    name="mooring_catenary_line",
    description=(
        "Single-segment catenary mooring line analysis.\n"
        "\n"
        "Computes suspended length, touchdown, horizontal and vertical tensions "
        "at fairlead and anchor, catenary parameter, horizontal and vertical spans, "
        "scope, and line profile for an inextensible or elastic catenary.\n"
        "\n"
        "Returns H_N, V_fairlead_N, T_fairlead_N, V_anchor_N, T_anchor_N, "
        "angle_fairlead_deg, angle_anchor_deg, catenary_param_m, "
        "horizontal_span_m, vertical_span_m, arc_length_m, touchdown_m, "
        "scope, profile_x, profile_z, and warnings.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises.\n"
        "\n"
        "References: Faltinsen (1990); API RP 2SK §3."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "w": {
                "type": "number",
                "description": "Submerged weight per unit length (N/m). Must be > 0.",
            },
            "L": {
                "type": "number",
                "description": "Unstretched suspended line length (m). Must be > 0.",
            },
            "H": {
                "type": "number",
                "description": "Horizontal tension component at fairlead (N). Must be > 0.",
            },
            "EA": {
                "type": "number",
                "description": (
                    "Axial stiffness (N). If supplied, elastic catenary is used. "
                    "Must be > 0."
                ),
            },
            "water_depth": {
                "type": "number",
                "description": (
                    "Water depth at anchor (m). If supplied, touchdown and scope "
                    "are computed and warnings for excessive/insufficient scope issued. "
                    "Must be > 0."
                ),
            },
            "n_profile_pts": {
                "type": "integer",
                "description": "Number of profile points (default 50). Must be > 1.",
            },
        },
        "required": ["w", "L", "H"],
    },
)


@register(_catenary_line_spec, write=False)
async def run_catenary_line(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("w", "L", "H"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "EA" in a:
        kwargs["EA"] = a["EA"]
    if "water_depth" in a:
        kwargs["water_depth"] = a["water_depth"]
    if "n_profile_pts" in a:
        kwargs["n_profile_pts"] = a["n_profile_pts"]

    result = catenary_line(a["w"], a["L"], a["H"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: mooring_multiseg_catenary
# ---------------------------------------------------------------------------

_multiseg_catenary_spec = ToolSpec(
    name="mooring_multiseg_catenary",
    description=(
        "Multi-segment catenary mooring line analysis (e.g. chain + wire + chain).\n"
        "\n"
        "Each segment is treated as an independent inextensible catenary sharing "
        "the same horizontal tension H.  Vertical loads accumulate from anchor "
        "to fairlead.\n"
        "\n"
        "Returns total T_fairlead_N, V_fairlead_N, total spans, and per-segment "
        "catenary results.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "segments": {
                "type": "array",
                "description": (
                    "Ordered list of segments from anchor to fairlead. "
                    "Each item: {\"w\": N/m, \"L\": m, \"label\": str (optional)}."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "w": {"type": "number", "description": "Submerged unit weight (N/m)."},
                        "L": {"type": "number", "description": "Segment length (m)."},
                        "label": {"type": "string", "description": "Segment label (optional)."},
                    },
                    "required": ["w", "L"],
                },
            },
            "H": {
                "type": "number",
                "description": "Horizontal tension component (N). Must be > 0.",
            },
        },
        "required": ["segments", "H"],
    },
)


@register(_multiseg_catenary_spec, write=False)
async def run_multiseg_catenary(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("segments") is None:
        return json.dumps({"ok": False, "reason": "segments is required"})
    if a.get("H") is None:
        return json.dumps({"ok": False, "reason": "H is required"})

    result = multiseg_catenary(a["segments"], a["H"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: mooring_system_stiffness
# ---------------------------------------------------------------------------

_mooring_system_spec = ToolSpec(
    name="mooring_system_stiffness",
    description=(
        "Mooring-system restoring force vs vessel offset and system stiffness.\n"
        "\n"
        "Models a spread-mooring system with N lines arranged at specified azimuths. "
        "For each offset, each line's catenary tension is recomputed.  Returns "
        "restoring force (N), linearised stiffness (N/m), and max line tension "
        "at each offset point.\n"
        "\n"
        "Consistent with API RP 2SK §3.5 intent for quasi-static analysis.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "lines": {
                "type": "array",
                "description": (
                    "List of mooring lines. Each item: "
                    "{\"w\": N/m, \"L\": m, \"H0\": N pretension, "
                    "\"azimuth_deg\": 0–360°}."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "w": {"type": "number"},
                        "L": {"type": "number"},
                        "H0": {"type": "number"},
                        "azimuth_deg": {"type": "number"},
                    },
                    "required": ["w", "L", "H0", "azimuth_deg"],
                },
            },
            "water_depth": {
                "type": "number",
                "description": "Water depth (m). Must be > 0.",
            },
            "fairlead_radius": {
                "type": "number",
                "description": "Horizontal distance vessel centre to fairlead (m). Must be > 0.",
            },
            "offsets": {
                "type": "array",
                "items": {"type": "number"},
                "description": "List of vessel offset values in surge direction (m).",
            },
        },
        "required": ["lines", "water_depth", "fairlead_radius", "offsets"],
    },
)


@register(_mooring_system_spec, write=False)
async def run_mooring_system(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("lines", "water_depth", "fairlead_radius", "offsets"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = mooring_system(
        a["lines"], a["water_depth"], a["fairlead_radius"], a["offsets"]
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: mooring_anchor_holding
# ---------------------------------------------------------------------------

_anchor_holding_spec = ToolSpec(
    name="mooring_anchor_holding",
    description=(
        "Simplified anchor holding capacity for drag-embedment, pile, or "
        "suction-caisson anchors.\n"
        "\n"
        "anchor_type='drag_embedment': H = holding_factor × anchor_weight_kN\n"
        "  Factors: soft_clay=30, stiff_clay=16, sand=10, rock=2\n"
        "  (Neubecker & Randolph 1996 simplified)\n"
        "\n"
        "anchor_type='pile': H = 9 × Su × D × L\n"
        "  (API RP 2SK Appendix C simplified, uniform Su)\n"
        "\n"
        "anchor_type='suction_caisson': H = Su × D × L × 10\n"
        "  (DNV-OS-E301 §6 simplified)\n"
        "\n"
        "Returns holding_kN, method_note, and site-specific warnings.\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "anchor_type": {
                "type": "string",
                "enum": ["drag_embedment", "pile", "suction_caisson"],
                "description": "Anchor type.",
            },
            "anchor_weight_kN": {
                "type": "number",
                "description": "Anchor dry weight (kN). Required for drag_embedment.",
            },
            "soil_type": {
                "type": "string",
                "enum": ["soft_clay", "stiff_clay", "sand", "rock"],
                "description": "Soil type for drag_embedment (default 'soft_clay').",
            },
            "pile_diameter_m": {
                "type": "number",
                "description": "Pile outer diameter (m). Required for pile.",
            },
            "pile_length_m": {
                "type": "number",
                "description": "Embedded pile length (m). Required for pile.",
            },
            "Su_kPa": {
                "type": "number",
                "description": "Undrained shear strength (kPa). Required for pile.",
            },
            "caisson_diameter_m": {
                "type": "number",
                "description": "Suction caisson outer diameter (m). Required for suction_caisson.",
            },
            "caisson_length_m": {
                "type": "number",
                "description": "Suction caisson skirt length (m). Required for suction_caisson.",
            },
            "Su_avg_kPa": {
                "type": "number",
                "description": "Average undrained shear strength (kPa). Required for suction_caisson.",
            },
        },
        "required": ["anchor_type"],
    },
)


@register(_anchor_holding_spec, write=False)
async def run_anchor_holding(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("anchor_type") is None:
        return json.dumps({"ok": False, "reason": "anchor_type is required"})

    kwargs: dict = {}
    for k in (
        "anchor_weight_kN", "soil_type",
        "pile_diameter_m", "pile_length_m", "Su_kPa",
        "caisson_diameter_m", "caisson_length_m", "Su_avg_kPa",
    ):
        if k in a:
            kwargs[k] = a[k]

    result = anchor_holding(a["anchor_type"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: mooring_morison_force
# ---------------------------------------------------------------------------

_morison_spec = ToolSpec(
    name="mooring_morison_force",
    description=(
        "Morison equation: wave + current drag and inertia force on a vertical "
        "circular cylinder.\n"
        "\n"
        "Uses F/L = ½ρCd·D·|u_r|u_r + ρCm(πD²/4)·du_w/dt\n"
        "where u_r = U_w + U_c (wave + current velocity).\n"
        "Returns F_drag_max_N, F_inertia_max_N, F_total_max_N (conservative sum), "
        "Keulegan-Carpenter number KC, and approximate Reynolds number Re.\n"
        "\n"
        "Warnings issued for KC < 5 (inertia dominated) or KC > 40 (drag dominated).\n"
        "\n"
        "Reference: Morison et al. (1950).  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "D": {"type": "number", "description": "Cylinder diameter (m). Must be > 0."},
            "L": {"type": "number", "description": "Cylinder length (m). Must be > 0."},
            "rho": {
                "type": "number",
                "description": "Water density (kg/m³). Must be > 0. Typical: 1025.",
            },
            "Cd": {
                "type": "number",
                "description": "Drag coefficient (dimensionless). Typical: 0.6–1.2.",
            },
            "Cm": {
                "type": "number",
                "description": "Inertia coefficient (Ca+1). Typical: 2.0.",
            },
            "U_c": {
                "type": "number",
                "description": "Current velocity (m/s). Must be >= 0.",
            },
            "U_w": {
                "type": "number",
                "description": "Wave-particle velocity amplitude (m/s). Must be >= 0.",
            },
            "omega": {
                "type": "number",
                "description": "Wave angular frequency (rad/s). Must be > 0.",
            },
            "k": {
                "type": "number",
                "description": "Wave number (rad/m). Must be > 0.",
            },
            "z": {
                "type": "number",
                "description": "Depth below mean water level (m, negative downward). Default 0.",
            },
        },
        "required": ["D", "L", "rho", "Cd", "Cm", "U_c", "U_w", "omega", "k"],
    },
)


@register(_morison_spec, write=False)
async def run_morison_force(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("D", "L", "rho", "Cd", "Cm", "U_c", "U_w", "omega", "k"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "z" in a:
        kwargs["z"] = a["z"]

    result = morison_wave_current(
        a["D"], a["L"], a["rho"], a["Cd"], a["Cm"],
        a["U_c"], a["U_w"], a["omega"], a["k"],
        **kwargs,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: mooring_mean_env_load
# ---------------------------------------------------------------------------

_mean_env_spec = ToolSpec(
    name="mooring_mean_env_load",
    description=(
        "Mean wind and current drag force on a vessel hull (OCIMF-style simplified).\n"
        "\n"
        "Uses F = ½ρCdAV² for wind and current.\n"
        "Returns F_wind_N, F_current_N, F_total_N.\n"
        "\n"
        "Note: OCIMF MEG3 recommends tabulated Cx/Cy per vessel type; "
        "this function is a simplified preliminary estimate assuming collinear loads.\n"
        "\n"
        "Errors: {ok:false, reason}.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "hull_area_wind": {
                "type": "number",
                "description": "Projected wind-exposed hull area (m²). Must be > 0.",
            },
            "Cd_wind": {
                "type": "number",
                "description": "Wind drag coefficient. Typical: 1.0–1.3.",
            },
            "rho_air": {
                "type": "number",
                "description": "Air density (kg/m³). Typical: 1.225.",
            },
            "V_wind": {
                "type": "number",
                "description": "Wind speed (m/s). Must be >= 0.",
            },
            "hull_area_current": {
                "type": "number",
                "description": "Projected current-exposed hull area (m²). Must be > 0.",
            },
            "Cd_current": {
                "type": "number",
                "description": "Current drag coefficient. Typical: 0.5–1.5.",
            },
            "rho_water": {
                "type": "number",
                "description": "Water density (kg/m³). Typical: 1025.",
            },
            "V_current": {
                "type": "number",
                "description": "Current speed (m/s). Must be >= 0.",
            },
        },
        "required": [
            "hull_area_wind", "Cd_wind", "rho_air", "V_wind",
            "hull_area_current", "Cd_current", "rho_water", "V_current",
        ],
    },
)


@register(_mean_env_spec, write=False)
async def run_mean_env_load(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in (
        "hull_area_wind", "Cd_wind", "rho_air", "V_wind",
        "hull_area_current", "Cd_current", "rho_water", "V_current",
    ):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = mean_env_load(
        a["hull_area_wind"], a["Cd_wind"], a["rho_air"], a["V_wind"],
        a["hull_area_current"], a["Cd_current"], a["rho_water"], a["V_current"],
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: mooring_watch_circle
# ---------------------------------------------------------------------------

_watch_circle_spec = ToolSpec(
    name="mooring_watch_circle",
    description=(
        "Watch circle and maximum permissible offset check per API RP 2SK §3.3.\n"
        "\n"
        "Default limit: max offset ≤ 5% of water depth.\n"
        "Takes the output of mooring_system_stiffness as input (system_result).\n"
        "\n"
        "Returns max_offset_m, watch_circle_radius_m, offset_exceeded flag, "
        "and critical_offset_m (first offset violating limit).\n"
        "\n"
        "Errors: {ok:false, reason}.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "system_result": {
                "type": "object",
                "description": "Output dict from mooring_system_stiffness tool.",
            },
            "max_offset_fraction": {
                "type": "number",
                "description": "Max offset as fraction of water depth (default 0.05 = 5%).",
            },
            "water_depth": {
                "type": "number",
                "description": "Water depth (m). Must be > 0 if supplied.",
            },
        },
        "required": ["system_result"],
    },
)


@register(_watch_circle_spec, write=False)
async def run_watch_circle(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("system_result") is None:
        return json.dumps({"ok": False, "reason": "system_result is required"})

    kwargs: dict = {}
    if "max_offset_fraction" in a:
        kwargs["max_offset_fraction"] = a["max_offset_fraction"]
    if "water_depth" in a:
        kwargs["water_depth"] = a["water_depth"]

    result = watch_circle(a["system_result"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: mooring_line_sf
# ---------------------------------------------------------------------------

_line_sf_spec = ToolSpec(
    name="mooring_line_sf",
    description=(
        "Line tension safety factor and API RP 2SK compliance check.\n"
        "\n"
        "API RP 2SK Table 3-1 requirements:\n"
        "  Intact condition (all lines):      SF ≥ 1.67 (60% MBL)\n"
        "  Damaged condition (one line lost): SF ≥ 1.25 (80% MBL)\n"
        "\n"
        "Returns SF_actual, pass_sf flag, utilisation_pct, and warnings "
        "if line is overtensioned.\n"
        "\n"
        "Errors: {ok:false, reason}.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "T_applied_kN": {
                "type": "number",
                "description": "Applied line tension (kN). Must be > 0.",
            },
            "T_break_kN": {
                "type": "number",
                "description": "Minimum breaking load MBL (kN). Must be > 0.",
            },
            "sf_required": {
                "type": "number",
                "description": (
                    "Required safety factor (default 1.67 for intact condition; "
                    "use 1.25 for damaged condition)."
                ),
            },
        },
        "required": ["T_applied_kN", "T_break_kN"],
    },
)


@register(_line_sf_spec, write=False)
async def run_line_sf(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("T_applied_kN", "T_break_kN"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "sf_required" in a:
        kwargs["sf_required"] = a["sf_required"]

    result = line_safety_factor(a["T_applied_kN"], a["T_break_kN"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: mooring_riser_top_tension
# ---------------------------------------------------------------------------

_riser_spec = ToolSpec(
    name="mooring_riser_top_tension",
    description=(
        "Riser top tension for a straight (or inclined) riser string.\n"
        "\n"
        "T_top = T_bottom + w_r × L_r × cos(θ)\n"
        "\n"
        "Returns T_top_N, H_top_N (horizontal component), weight_component_N.\n"
        "Warning issued if inclination θ > 15° (catenary analysis recommended).\n"
        "\n"
        "Reference: API RP 16Q / DNV-OS-F201.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "w_r": {
                "type": "number",
                "description": "Effective submerged weight per unit length (N/m). Must be > 0.",
            },
            "L_r": {
                "type": "number",
                "description": "Riser length (m). Must be > 0.",
            },
            "T_bottom": {
                "type": "number",
                "description": "Tension at bottom connector (N). Must be >= 0.",
            },
            "theta_deg": {
                "type": "number",
                "description": "Riser inclination from vertical (°). Default 0. Range [0, 89.9].",
            },
        },
        "required": ["w_r", "L_r", "T_bottom"],
    },
)


@register(_riser_spec, write=False)
async def run_riser_top_tension(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("w_r", "L_r", "T_bottom"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "theta_deg" in a:
        kwargs["theta_deg"] = a["theta_deg"]

    result = riser_top_tension(a["w_r"], a["L_r"], a["T_bottom"], **kwargs)
    return ok_payload(result)
