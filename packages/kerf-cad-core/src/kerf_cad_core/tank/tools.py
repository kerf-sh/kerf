"""
kerf_cad_core.tank.tools — LLM tool wrappers for API 650 atmospheric
storage-tank design.

Registers fifteen tools with the Kerf tool registry:

  tank_shell_course_thickness     — §5.6 1-foot & variable-design-point
  tank_minimum_shell_thickness    — Table 5-6a minimum thickness by diameter
  tank_bottom_plate_thickness     — §5.4 bottom plate minimum
  tank_annular_plate_thickness    — §5.5 annular bottom plate
  tank_cone_roof_thickness        — §5.10.5.1 cone roof (supported & self-sup.)
  tank_dome_roof_thickness        — §5.10.5.2 dome roof (self-supporting)
  tank_wind_girder_section_modulus— §5.9.7 top wind girder
  tank_intermediate_stiffener     — §5.9.7.3 intermediate stiffener spacing
  tank_overturning_stability      — §5.11 wind overturning check
  tank_anchorage_requirement      — §5.11.2 anchor bolt sizing
  tank_seismic_annex_e            — Annex E seismic: base shear + sloshing
  tank_venting_normal             — API 2000 §4 normal venting
  tank_venting_emergency          — API 2000 §5 emergency venting (fire)
  tank_settlement_check           — App. B edge/planar/differential settlement
  tank_nozzle_reinforcement       — §5.7 nozzle reinforcement area check

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
API Standard 650, 13th Edition, 2020
API Standard 2000, 7th Edition, 2014

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.tank.api650 import (
    shell_course_thickness,
    minimum_shell_thickness,
    bottom_plate_thickness,
    annular_plate_thickness,
    cone_roof_thickness,
    dome_roof_thickness,
    wind_girder_section_modulus,
    intermediate_stiffener_spacing,
    overturning_stability,
    anchorage_requirement,
    seismic_annex_e,
    venting_normal,
    venting_emergency,
    settlement_check,
    nozzle_reinforcement_note,
)


# ---------------------------------------------------------------------------
# Tool: tank_shell_course_thickness
# ---------------------------------------------------------------------------

_shell_course_spec = ToolSpec(
    name="tank_shell_course_thickness",
    description=(
        "Compute required shell-plate thickness for one course of an API 650 "
        "atmospheric storage tank.\n"
        "\n"
        "Two methods:\n"
        "  '1-foot' (default) — design point 0.3 m above course bottom (§5.6.3.1).\n"
        "  'variable'         — user-specified design-point height x above bottom (§5.6.3.2).\n"
        "\n"
        "Returns net product load thickness, hydrotest thickness, and required "
        "thickness (governing + corrosion allowance).  Flags under-thickness in warnings."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "D": {"type": "number", "description": "Nominal tank diameter (m). Must be > 0."},
            "H": {"type": "number", "description": "Design liquid height above bottom of course (m). Must be > 0."},
            "G": {"type": "number", "description": "Design specific gravity of liquid (default 1.0)."},
            "Sd": {"type": "number", "description": "Allowable stress — product load (Pa, default 160e6)."},
            "St": {"type": "number", "description": "Allowable stress — hydrotest load (Pa, default 171e6)."},
            "c": {"type": "number", "description": "Corrosion allowance (m, default 0)."},
            "method": {"type": "string", "enum": ["1-foot", "variable"], "description": "Design method."},
            "x": {"type": "number", "description": "Design-point height above course bottom (m). Required for method='variable'."},
        },
        "required": ["D", "H"],
    },
)


@register(_shell_course_spec, write=False)
async def run_tank_shell_course_thickness(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if a.get("D") is None:
        return json.dumps({"ok": False, "reason": "D is required"})
    if a.get("H") is None:
        return json.dumps({"ok": False, "reason": "H is required"})
    kwargs: dict = {}
    for k in ("G", "Sd", "St", "c", "method", "x"):
        if k in a:
            kwargs[k] = a[k]
    return ok_payload(shell_course_thickness(a["D"], a["H"], **kwargs))


# ---------------------------------------------------------------------------
# Tool: tank_minimum_shell_thickness
# ---------------------------------------------------------------------------

_min_shell_spec = ToolSpec(
    name="tank_minimum_shell_thickness",
    description=(
        "Return the API 650 Table 5-6a minimum permissible shell-plate thickness "
        "for a given nominal tank diameter.\n"
        "\n"
        "  D ≤ 15 m  → 5 mm\n"
        "  15 < D ≤ 30 m → 6 mm\n"
        "  30 < D ≤ 60 m → 8 mm\n"
        "  D > 60 m  → 10 mm"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "D": {"type": "number", "description": "Nominal tank diameter (m). Must be > 0."},
        },
        "required": ["D"],
    },
)


@register(_min_shell_spec, write=False)
async def run_tank_minimum_shell_thickness(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if a.get("D") is None:
        return json.dumps({"ok": False, "reason": "D is required"})
    return ok_payload(minimum_shell_thickness(a["D"]))


# ---------------------------------------------------------------------------
# Tool: tank_bottom_plate_thickness
# ---------------------------------------------------------------------------

_bottom_plate_spec = ToolSpec(
    name="tank_bottom_plate_thickness",
    description=(
        "Return the API 650 §5.4.1 minimum bottom plate thickness.\n"
        "\n"
        "The absolute minimum is 6 mm net; corrosion allowance is added on top.\n"
        "Flags large corrosion allowances without cathodic protection."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "c": {"type": "number", "description": "Corrosion allowance (m, default 0)."},
            "has_liner": {"type": "boolean", "description": "True if sacrificial liner present (default false)."},
        },
        "required": [],
    },
)


@register(_bottom_plate_spec, write=False)
async def run_tank_bottom_plate_thickness(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    kwargs: dict = {}
    if "c" in a:
        kwargs["c"] = a["c"]
    if "has_liner" in a:
        kwargs["has_liner"] = a["has_liner"]
    return ok_payload(bottom_plate_thickness(**kwargs))


# ---------------------------------------------------------------------------
# Tool: tank_annular_plate_thickness
# ---------------------------------------------------------------------------

_annular_spec = ToolSpec(
    name="tank_annular_plate_thickness",
    description=(
        "Compute the minimum annular bottom plate thickness per API 650 §5.5.\n"
        "\n"
        "Thickness is governed by the hydrostatic product pressure at the base "
        "of the first shell course (API 650 Table 5-1a).\n"
        "Minimum annular plate projection beyond shell ≥ 600 mm."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "D": {"type": "number", "description": "Nominal tank diameter (m). Must be > 0."},
            "H": {"type": "number", "description": "Maximum design liquid height (m). Must be > 0."},
            "G": {"type": "number", "description": "Specific gravity (default 1.0)."},
            "Fy_shell_Pa": {"type": "number", "description": "First-shell-course yield strength (Pa, default 250e6)."},
            "c": {"type": "number", "description": "Corrosion allowance (m, default 0)."},
        },
        "required": ["D", "H"],
    },
)


@register(_annular_spec, write=False)
async def run_tank_annular_plate_thickness(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if a.get("D") is None:
        return json.dumps({"ok": False, "reason": "D is required"})
    if a.get("H") is None:
        return json.dumps({"ok": False, "reason": "H is required"})
    kwargs: dict = {}
    for k in ("G", "Fy_shell_Pa", "c"):
        if k in a:
            kwargs[k] = a[k]
    return ok_payload(annular_plate_thickness(a["D"], a["H"], **kwargs))


# ---------------------------------------------------------------------------
# Tool: tank_cone_roof_thickness
# ---------------------------------------------------------------------------

_cone_roof_spec = ToolSpec(
    name="tank_cone_roof_thickness",
    description=(
        "Required cone-roof plate thickness per API 650 §5.10.5.1.\n"
        "\n"
        "Supports two sub-cases:\n"
        "  Supported cone (self_supporting=false): rafters carry load; "
        "    minimum net thickness = 5 mm.\n"
        "  Self-supporting cone (self_supporting=true): membrane formula "
        "    N_m = w·D/(4·sin θ); t = N_m/(Sd·E).\n"
        "\n"
        "Cone half-angle θ must be between 9.46° and 37°.\n"
        "Also returns frangible_joint flag (API 650 Appendix F)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "D": {"type": "number", "description": "Nominal tank diameter (m). Must be > 0."},
            "theta_deg": {"type": "number", "description": "Cone half-angle from horizontal (°, default 9.46°, range 9.46–37°)."},
            "design_load_Pa": {"type": "number", "description": "Uniform design roof load (Pa, default 1200 Pa)."},
            "Sd": {"type": "number", "description": "Allowable stress (Pa, default 160e6)."},
            "E_joint": {"type": "number", "description": "Weld joint efficiency (default 1.0)."},
            "c": {"type": "number", "description": "Corrosion allowance (m, default 0)."},
            "self_supporting": {"type": "boolean", "description": "True for self-supporting cone (default false)."},
        },
        "required": ["D"],
    },
)


@register(_cone_roof_spec, write=False)
async def run_tank_cone_roof_thickness(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if a.get("D") is None:
        return json.dumps({"ok": False, "reason": "D is required"})
    kwargs: dict = {}
    for k in ("theta_deg", "design_load_Pa", "Sd", "E_joint", "c", "self_supporting"):
        if k in a:
            kwargs[k] = a[k]
    return ok_payload(cone_roof_thickness(a["D"], **kwargs))


# ---------------------------------------------------------------------------
# Tool: tank_dome_roof_thickness
# ---------------------------------------------------------------------------

_dome_roof_spec = ToolSpec(
    name="tank_dome_roof_thickness",
    description=(
        "Required self-supporting dome-roof plate thickness per API 650 §5.10.5.2.\n"
        "\n"
        "Membrane formula: t = w·Rc/(2·Sd·E).\n"
        "Crown radius 0.8 D ≤ Rc ≤ 1.5 D; defaults to 0.8 D (most conservative).\n"
        "Minimum net thickness = 5 mm."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "D": {"type": "number", "description": "Nominal tank diameter (m). Must be > 0."},
            "Rc": {"type": "number", "description": "Crown radius (m, default 0.8 D)."},
            "design_load_Pa": {"type": "number", "description": "Uniform design roof load (Pa, default 1200 Pa)."},
            "Sd": {"type": "number", "description": "Allowable stress (Pa, default 160e6)."},
            "E_joint": {"type": "number", "description": "Weld joint efficiency (default 1.0)."},
            "c": {"type": "number", "description": "Corrosion allowance (m, default 0)."},
        },
        "required": ["D"],
    },
)


@register(_dome_roof_spec, write=False)
async def run_tank_dome_roof_thickness(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if a.get("D") is None:
        return json.dumps({"ok": False, "reason": "D is required"})
    kwargs: dict = {}
    for k in ("Rc", "design_load_Pa", "Sd", "E_joint", "c"):
        if k in a:
            kwargs[k] = a[k]
    return ok_payload(dome_roof_thickness(a["D"], **kwargs))


# ---------------------------------------------------------------------------
# Tool: tank_wind_girder_section_modulus
# ---------------------------------------------------------------------------

_wind_girder_spec = ToolSpec(
    name="tank_wind_girder_section_modulus",
    description=(
        "Required section modulus of the top wind girder per API 650 §5.9.7.1.\n"
        "\n"
        "Z [m³] = 0.0001 × D² × H × (V/190)²  (V in km/h, D/H in m).\n"
        "\n"
        "Also computes maximum unstiffened shell height W_max per §5.9.7.3 "
        "and warns if shell height exceeds W_max (intermediate stiffeners needed)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "D": {"type": "number", "description": "Nominal tank diameter (m). Must be > 0."},
            "t_shell": {"type": "number", "description": "Shell plate thickness (m). Must be > 0."},
            "V_wind_m_s": {"type": "number", "description": "Design wind speed (m/s, default 45 m/s)."},
            "H_shell": {"type": "number", "description": "Total shell height (m, optional — enables max-height check)."},
        },
        "required": ["D", "t_shell"],
    },
)


@register(_wind_girder_spec, write=False)
async def run_tank_wind_girder_section_modulus(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if a.get("D") is None:
        return json.dumps({"ok": False, "reason": "D is required"})
    if a.get("t_shell") is None:
        return json.dumps({"ok": False, "reason": "t_shell is required"})
    kwargs: dict = {}
    for k in ("V_wind_m_s", "H_shell"):
        if k in a:
            kwargs[k] = a[k]
    return ok_payload(wind_girder_section_modulus(a["D"], a["t_shell"], **kwargs))


# ---------------------------------------------------------------------------
# Tool: tank_intermediate_stiffener
# ---------------------------------------------------------------------------

_inter_stiff_spec = ToolSpec(
    name="tank_intermediate_stiffener",
    description=(
        "Maximum intermediate wind stiffener spacing per API 650 §5.9.7.3.\n"
        "\n"
        "W_max [m] = (9.47 × t × (190/V))^(1/3)  (V in km/h, t in m).\n"
        "\n"
        "Returns W_max, the minimum number of intermediate stiffeners, and "
        "the resulting even spacing if stiffeners are placed."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "D": {"type": "number", "description": "Nominal tank diameter (m). Must be > 0."},
            "t_shell": {"type": "number", "description": "Minimum shell plate thickness in the region (m). Must be > 0."},
            "H_shell": {"type": "number", "description": "Total shell height (m). Must be > 0."},
            "V_wind_m_s": {"type": "number", "description": "Design wind speed (m/s, default 45 m/s)."},
        },
        "required": ["D", "t_shell", "H_shell"],
    },
)


@register(_inter_stiff_spec, write=False)
async def run_tank_intermediate_stiffener(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for f in ("D", "t_shell", "H_shell"):
        if a.get(f) is None:
            return json.dumps({"ok": False, "reason": f"{f} is required"})
    kwargs: dict = {}
    if "V_wind_m_s" in a:
        kwargs["V_wind_m_s"] = a["V_wind_m_s"]
    return ok_payload(intermediate_stiffener_spacing(a["D"], a["t_shell"], a["H_shell"], **kwargs))


# ---------------------------------------------------------------------------
# Tool: tank_overturning_stability
# ---------------------------------------------------------------------------

_overturning_spec = ToolSpec(
    name="tank_overturning_stability",
    description=(
        "Wind overturning stability check per API 650 §5.11.\n"
        "\n"
        "Overturning moment: M = 0.5 ρ_air V² × Cf × D × H × H/2.\n"
        "Resisting moment: M_r = W_dead × D/2 + W_liquid × D/4.\n"
        "SF = M_resist / M_wind; must be ≥ 1.5.  Flags overturning in warnings."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "D": {"type": "number", "description": "Nominal tank diameter (m). Must be > 0."},
            "H_shell": {"type": "number", "description": "Shell height (m). Must be > 0."},
            "W_total_N": {"type": "number", "description": "Total tank dead-weight empty (N). Must be > 0."},
            "V_wind_m_s": {"type": "number", "description": "Design wind speed (m/s, default 45)."},
            "rho_air": {"type": "number", "description": "Air density (kg/m³, default 1.225)."},
            "Cf": {"type": "number", "description": "Wind force coefficient (default 0.7)."},
            "H_liquid_m": {"type": "number", "description": "Liquid height for partial-fill check (m, default 0)."},
            "rho_liquid": {"type": "number", "description": "Liquid density (kg/m³, default 1000)."},
        },
        "required": ["D", "H_shell", "W_total_N"],
    },
)


@register(_overturning_spec, write=False)
async def run_tank_overturning_stability(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for f in ("D", "H_shell", "W_total_N"):
        if a.get(f) is None:
            return json.dumps({"ok": False, "reason": f"{f} is required"})
    kwargs: dict = {}
    for k in ("V_wind_m_s", "rho_air", "Cf", "H_liquid_m", "rho_liquid"):
        if k in a:
            kwargs[k] = a[k]
    return ok_payload(overturning_stability(a["D"], a["H_shell"], a["W_total_N"], **kwargs))


# ---------------------------------------------------------------------------
# Tool: tank_anchorage_requirement
# ---------------------------------------------------------------------------

_anchorage_spec = ToolSpec(
    name="tank_anchorage_requirement",
    description=(
        "Anchor bolt sizing per API 650 §5.11.2.\n"
        "\n"
        "Net uplift = 2M/D - W_shell.  Required bolt area = F_per_bolt / sigma_allow.\n"
        "Supported bolt grades: 'A307' (124 MPa), 'A193-B7' (207 MPa), 'A36' (96 MPa).\n"
        "Returns zero area if no net uplift exists."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "D": {"type": "number", "description": "Nominal tank diameter (m). Must be > 0."},
            "M_overturning_Nm": {"type": "number", "description": "Net overturning moment (N·m). Must be >= 0."},
            "W_shell_N": {"type": "number", "description": "Shell + roof dead weight (N). Must be > 0."},
            "n_bolts": {"type": "integer", "description": "Number of anchor bolts (default 16, min 4)."},
            "bolt_grade": {"type": "string", "enum": ["A307", "A193-B7", "A36"], "description": "Bolt material grade (default 'A307')."},
            "safety_factor": {"type": "number", "description": "Safety factor on bolt allowable (default 2.0)."},
        },
        "required": ["D", "M_overturning_Nm", "W_shell_N"],
    },
)


@register(_anchorage_spec, write=False)
async def run_tank_anchorage_requirement(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for f in ("D", "M_overturning_Nm", "W_shell_N"):
        if a.get(f) is None:
            return json.dumps({"ok": False, "reason": f"{f} is required"})
    kwargs: dict = {}
    for k in ("bolt_grade", "safety_factor"):
        if k in a:
            kwargs[k] = a[k]
    if "n_bolts" in a:
        kwargs["n_bolts"] = int(a["n_bolts"])
    return ok_payload(anchorage_requirement(a["D"], a["M_overturning_Nm"], a["W_shell_N"], **kwargs))


# ---------------------------------------------------------------------------
# Tool: tank_seismic_annex_e
# ---------------------------------------------------------------------------

_seismic_spec = ToolSpec(
    name="tank_seismic_annex_e",
    description=(
        "API 650 Annex E seismic design — impulsive/convective masses, "
        "base shear, overturning moment, sloshing wave height, and freeboard.\n"
        "\n"
        "Uses the Housner model for ground-supported vertical cylindrical tanks.\n"
        "Returns impulsive/convective mass fractions, periods, base shears (SRSS), "
        "overturning moments (SRSS), sloshing wave height delta_s, and required "
        "freeboard.  Flags inadequate freeboard in warnings."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "D": {"type": "number", "description": "Nominal inside diameter (m). Must be > 0."},
            "H_liquid": {"type": "number", "description": "Maximum design liquid height (m). Must be > 0."},
            "rho_liquid": {"type": "number", "description": "Liquid density (kg/m³, default 1000)."},
            "Sds": {"type": "number", "description": "Short-period spectral acceleration (g, default 0.5)."},
            "Sd1": {"type": "number", "description": "1-second spectral acceleration (g, default 0.2)."},
            "I": {"type": "number", "description": "Importance factor (default 1.0)."},
        },
        "required": ["D", "H_liquid"],
    },
)


@register(_seismic_spec, write=False)
async def run_tank_seismic_annex_e(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for f in ("D", "H_liquid"):
        if a.get(f) is None:
            return json.dumps({"ok": False, "reason": f"{f} is required"})
    kwargs: dict = {}
    for k in ("rho_liquid", "Sds", "Sd1", "I"):
        if k in a:
            kwargs[k] = a[k]
    return ok_payload(seismic_annex_e(a["D"], a["H_liquid"], **kwargs))


# ---------------------------------------------------------------------------
# Tool: tank_venting_normal
# ---------------------------------------------------------------------------

_vent_normal_spec = ToolSpec(
    name="tank_venting_normal",
    description=(
        "Required normal vent capacity per API Standard 2000, 7th Ed., §4.\n"
        "\n"
        "Thermal breathing Vb ≈ 0.1 × V_tank [m³/h].\n"
        "Working vent = fill/drain rate × 3600.\n"
        "Returns in-breathing and out-breathing totals.  Flags Class I service "
        "(flash point < 37.8°C) and large tanks (> 56,800 m³)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "V_tank_m3": {"type": "number", "description": "Tank capacity (m³). Must be > 0."},
            "flash_point_C": {"type": "number", "description": "Product flash point (°C, default 40)."},
            "fill_rate_m3_s": {"type": "number", "description": "Maximum fill rate (m³/s, default 0)."},
            "draw_rate_m3_s": {"type": "number", "description": "Maximum draw rate (m³/s, default 0)."},
        },
        "required": ["V_tank_m3"],
    },
)


@register(_vent_normal_spec, write=False)
async def run_tank_venting_normal(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if a.get("V_tank_m3") is None:
        return json.dumps({"ok": False, "reason": "V_tank_m3 is required"})
    kwargs: dict = {}
    for k in ("flash_point_C", "fill_rate_m3_s", "draw_rate_m3_s"):
        if k in a:
            kwargs[k] = a[k]
    return ok_payload(venting_normal(a["V_tank_m3"], **kwargs))


# ---------------------------------------------------------------------------
# Tool: tank_venting_emergency
# ---------------------------------------------------------------------------

_vent_emergency_spec = ToolSpec(
    name="tank_venting_emergency",
    description=(
        "Required emergency vent capacity (fire case) per API 2000, §5.3.2.\n"
        "\n"
        "Q_fire [m³/h] = 3.091 × A_w^0.82  (A_w = wetted area in m²).\n"
        "\n"
        "Wetted area may be supplied directly or computed from D + H_liquid "
        "(wetted shell + bottom, max wetted height 9.14 m per API 2000)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "V_tank_m3": {"type": "number", "description": "Tank volume (m³, for validation). Must be > 0."},
            "wetted_area_m2": {"type": "number", "description": "Wetted surface area (m²). Provide this OR D + H_liquid."},
            "D": {"type": "number", "description": "Tank diameter (m, used to compute wetted area if wetted_area_m2 not given)."},
            "H_liquid": {"type": "number", "description": "Liquid height (m, used to compute wetted area if wetted_area_m2 not given)."},
        },
        "required": ["V_tank_m3"],
    },
)


@register(_vent_emergency_spec, write=False)
async def run_tank_venting_emergency(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if a.get("V_tank_m3") is None:
        return json.dumps({"ok": False, "reason": "V_tank_m3 is required"})
    kwargs: dict = {}
    if "wetted_area_m2" in a:
        kwargs["wetted_area_m2"] = a["wetted_area_m2"]
    if "D" in a:
        kwargs["D"] = a["D"]
    if "H_liquid" in a:
        kwargs["H_liquid"] = a["H_liquid"]
    return ok_payload(venting_emergency(a["V_tank_m3"], **kwargs))


# ---------------------------------------------------------------------------
# Tool: tank_settlement_check
# ---------------------------------------------------------------------------

_settlement_spec = ToolSpec(
    name="tank_settlement_check",
    description=(
        "API 650 Appendix B settlement tolerance checks.\n"
        "\n"
        "Checks three components:\n"
        "  Edge settlement    ≤ D×10 mm  (§B.4.2)\n"
        "  Planar tilt        ≤ D×10 mm  (§B.4.3)\n"
        "  Differential       ≤ 13 mm per 10° arc  (§B.4.4 conservative)\n"
        "\n"
        "Flags failing components with descriptive warnings."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "D": {"type": "number", "description": "Nominal tank diameter (m). Must be > 0."},
            "S_edge_mm": {"type": "number", "description": "Measured edge settlement (mm, default 0)."},
            "S_planar_mm": {"type": "number", "description": "Measured planar tilt differential (mm, default 0)."},
            "S_diff_max_mm": {"type": "number", "description": "Max differential between adjacent measurement points (mm, default 0)."},
            "measurement_arc_deg": {"type": "number", "description": "Arc angle between measurement points (degrees, default 10°)."},
        },
        "required": ["D"],
    },
)


@register(_settlement_spec, write=False)
async def run_tank_settlement_check(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if a.get("D") is None:
        return json.dumps({"ok": False, "reason": "D is required"})
    kwargs: dict = {}
    for k in ("S_edge_mm", "S_planar_mm", "S_diff_max_mm", "measurement_arc_deg"):
        if k in a:
            kwargs[k] = a[k]
    return ok_payload(settlement_check(a["D"], **kwargs))


# ---------------------------------------------------------------------------
# Tool: tank_nozzle_reinforcement
# ---------------------------------------------------------------------------

_nozzle_spec = ToolSpec(
    name="tank_nozzle_reinforcement",
    description=(
        "API 650 §5.7.3 nozzle reinforcement area-replacement check.\n"
        "\n"
        "A_required = d_nozzle × t_req  where t_req is the required shell "
        "thickness at nozzle elevation.\n"
        "Available area = excess shell area + nozzle neck area.\n"
        "Returns reinforcement_ok flag and shortfall if inadequate."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "D_shell": {"type": "number", "description": "Tank diameter (m). Must be > 0."},
            "t_shell": {"type": "number", "description": "Nominal shell thickness at nozzle elevation (m). Must be > 0."},
            "d_nozzle": {"type": "number", "description": "Nozzle inside diameter (m). Must be > 0."},
            "t_nozzle": {"type": "number", "description": "Nozzle neck nominal thickness (m). Must be > 0."},
            "H": {"type": "number", "description": "Liquid height above nozzle centreline (m). Must be > 0."},
            "G": {"type": "number", "description": "Specific gravity (default 1.0)."},
            "Sd": {"type": "number", "description": "Allowable stress (Pa, default 160e6)."},
            "c": {"type": "number", "description": "Corrosion allowance (m, default 0)."},
        },
        "required": ["D_shell", "t_shell", "d_nozzle", "t_nozzle", "H"],
    },
)


@register(_nozzle_spec, write=False)
async def run_tank_nozzle_reinforcement(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for f in ("D_shell", "t_shell", "d_nozzle", "t_nozzle", "H"):
        if a.get(f) is None:
            return json.dumps({"ok": False, "reason": f"{f} is required"})
    kwargs: dict = {}
    for k in ("G", "Sd", "c"):
        if k in a:
            kwargs[k] = a[k]
    return ok_payload(nozzle_reinforcement_note(
        a["D_shell"], a["t_shell"], a["d_nozzle"], a["t_nozzle"], a["H"], **kwargs
    ))
