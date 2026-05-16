"""
kerf_cad_core.navalarch.tools — LLM tool wrappers for hydrostatics & intact stability.

Registers the following tools with the Kerf tool registry:

  navalarch_displacement_LBT    — displacement from L/B/T & block coefficient
  navalarch_displacement_offsets— displacement from sectional-area curve (Simpson's)
  navalarch_form_coefficients   — Cb, Cp, Cm, Cw form coefficients
  navalarch_waterplane          — waterplane area, LCF, moments of inertia
  navalarch_vertical_centres    — KB (Morrish), KM
  navalarch_metacentric_height  — GM = KB + BM − KG, stability flag
  navalarch_righting_arm        — GZ small-angle + wall-sided correction
  navalarch_tpc_mctc            — TPC and MCT1cm
  navalarch_free_surface        — free-surface correction to GM
  navalarch_resistance          — Admiralty Coefficient power estimate
  navalarch_trim                — trim and draught change from moment

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
Barras, C.B. "Ship Stability for Masters and Mates", 6th ed.
Rawson & Tupper, "Basic Ship Theory", 5th ed.
ITTC 1978 Power Prediction Method.

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.navalarch.hydrostatics import (
    displacement_from_LBT,
    displacement_from_offsets,
    form_coefficients,
    waterplane_properties,
    vertical_centres,
    metacentric_height,
    righting_arm_GZ,
    tpc_mctc,
    free_surface_correction,
    resistance_admiralty,
    trim_from_moment,
)


# ---------------------------------------------------------------------------
# Tool: navalarch_displacement_LBT
# ---------------------------------------------------------------------------

_displacement_LBT_spec = ToolSpec(
    name="navalarch_displacement_LBT",
    description=(
        "Compute ship displacement volume and mass from principal dimensions "
        "and block coefficient.\n"
        "\n"
        "  ∇ = L × B × T × Cb   (m³)\n"
        "  W = ∇ × ρ / 1000      (tonnes)\n"
        "\n"
        "Returns volume_m3, displacement_t, displacement_kN (buoyancy force).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "L": {"type": "number", "description": "Length between perpendiculars (m). Must be > 0."},
            "B": {"type": "number", "description": "Moulded breadth (m). Must be > 0."},
            "T": {"type": "number", "description": "Mean moulded draught (m). Must be > 0."},
            "Cb": {"type": "number", "description": "Block coefficient (0 < Cb <= 1)."},
            "rho": {"type": "number", "description": "Water density (kg/m³). Default 1025 (sea water)."},
        },
        "required": ["L", "B", "T", "Cb"],
    },
)


@register(_displacement_LBT_spec, write=False)
async def run_navalarch_displacement_LBT(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("L", "B", "T", "Cb"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "rho" in a:
        kwargs["rho"] = a["rho"]

    result = displacement_from_LBT(a["L"], a["B"], a["T"], a["Cb"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: navalarch_displacement_offsets
# ---------------------------------------------------------------------------

_displacement_offsets_spec = ToolSpec(
    name="navalarch_displacement_offsets",
    description=(
        "Compute displacement from a tabulated sectional-area curve using "
        "Simpson's 1/3 rule (or trapezoidal if spacing is non-uniform).\n"
        "\n"
        "Provide longitudinal station positions (m from AP) and the submerged "
        "cross-sectional area at each station (m²).  At least 3 stations required "
        "for Simpson's rule.\n"
        "\n"
        "Returns volume_m3, displacement_t, LCB position from AP.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "stations": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Station positions from AP (m). Monotonically increasing. >= 3 values.",
            },
            "sectional_areas": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Submerged cross-sectional area at each station (m²). All >= 0.",
            },
            "rho": {"type": "number", "description": "Water density (kg/m³). Default 1025."},
        },
        "required": ["stations", "sectional_areas"],
    },
)


@register(_displacement_offsets_spec, write=False)
async def run_navalarch_displacement_offsets(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("stations") is None:
        return json.dumps({"ok": False, "reason": "stations is required"})
    if a.get("sectional_areas") is None:
        return json.dumps({"ok": False, "reason": "sectional_areas is required"})

    kwargs: dict = {}
    if "rho" in a:
        kwargs["rho"] = a["rho"]

    result = displacement_from_offsets(a["stations"], a["sectional_areas"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: navalarch_form_coefficients
# ---------------------------------------------------------------------------

_form_coeff_spec = ToolSpec(
    name="navalarch_form_coefficients",
    description=(
        "Compute the four primary naval architecture form coefficients:\n"
        "\n"
        "  Cb (block)      = ∇ / (L·B·T)\n"
        "  Cm (midship)    = Am / (B·T)\n"
        "  Cp (prismatic)  = Cb / Cm  = ∇ / (Am·L)\n"
        "  Cw (waterplane) = Aw / (L·B)\n"
        "\n"
        "Returns all four coefficients and the input parameters.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "L": {"type": "number", "description": "Length between perpendiculars (m). > 0."},
            "B": {"type": "number", "description": "Moulded breadth (m). > 0."},
            "T": {"type": "number", "description": "Moulded draught (m). > 0."},
            "Cb": {"type": "number", "description": "Block coefficient (0 < Cb <= 1)."},
            "Am": {"type": "number", "description": "Midship section area (m²). > 0."},
            "Aw": {"type": "number", "description": "Waterplane area (m²). > 0."},
        },
        "required": ["L", "B", "T", "Cb", "Am", "Aw"],
    },
)


@register(_form_coeff_spec, write=False)
async def run_navalarch_form_coefficients(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("L", "B", "T", "Cb", "Am", "Aw"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = form_coefficients(a["L"], a["B"], a["T"], a["Cb"], a["Am"], a["Aw"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: navalarch_waterplane
# ---------------------------------------------------------------------------

_waterplane_spec = ToolSpec(
    name="navalarch_waterplane",
    description=(
        "Compute waterplane area, centre of flotation (LCF), and second moments "
        "of area via Simpson's 1/3 rule from waterline half-breadths.\n"
        "\n"
        "  Aw   = 2 × ∫ y dx              (m²)\n"
        "  LCF  = (∫ x·y dx) / (∫ y dx)  (m from AP)\n"
        "  IL   = 2 × ∫ x²·y dx          (m⁴, about AP)\n"
        "  IT   = (2/3) × ∫ y³ dx        (m⁴, transverse about CL)\n"
        "\n"
        "Returns Aw_m2, LCF_fwd_AP, IL_m4, IL_LCF_m4, IT_m4.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "stations": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Longitudinal positions from AP (m). Monotonically increasing. >= 3 values.",
            },
            "half_breadths": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Half-breadths at waterline at each station (m). All >= 0.",
            },
        },
        "required": ["stations", "half_breadths"],
    },
)


@register(_waterplane_spec, write=False)
async def run_navalarch_waterplane(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("stations") is None:
        return json.dumps({"ok": False, "reason": "stations is required"})
    if a.get("half_breadths") is None:
        return json.dumps({"ok": False, "reason": "half_breadths is required"})

    result = waterplane_properties(a["stations"], a["half_breadths"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: navalarch_vertical_centres
# ---------------------------------------------------------------------------

_vert_centres_spec = ToolSpec(
    name="navalarch_vertical_centres",
    description=(
        "Estimate KB (height of centre of buoyancy above keel) using the "
        "Morrish/Murray formula:\n"
        "\n"
        "  Cw_est = (1 + 2·Cb) / 3           (Normand's approximation)\n"
        "  KB     = T × (5/6 − Cb/(3·Cw))    (Morrish/Murray)\n"
        "\n"
        "Also returns KB_box = T/2 (rectangular hull reference) and the estimated Cw.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "T": {"type": "number", "description": "Mean draught (m). > 0."},
            "Cb": {"type": "number", "description": "Block coefficient (0 < Cb <= 1)."},
        },
        "required": ["T", "Cb"],
    },
)


@register(_vert_centres_spec, write=False)
async def run_navalarch_vertical_centres(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("T", "Cb"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = vertical_centres(a["T"], a["Cb"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: navalarch_metacentric_height
# ---------------------------------------------------------------------------

_GM_spec = ToolSpec(
    name="navalarch_metacentric_height",
    description=(
        "Compute GM = KB + BM − KG and flag instability.\n"
        "\n"
        "BM (transverse) = IT / ∇\n"
        "GM > 0 → stable;  GM ≤ 0 → unstable (flagged in warnings).\n"
        "\n"
        "Returns GM_m, KM_m, stable flag, and warnings list.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "KB": {"type": "number", "description": "Height of centre of buoyancy above keel (m). >= 0."},
            "BM": {"type": "number", "description": "Metacentric radius (m). >= 0."},
            "KG": {"type": "number", "description": "Height of centre of gravity above keel (m). >= 0."},
        },
        "required": ["KB", "BM", "KG"],
    },
)


@register(_GM_spec, write=False)
async def run_navalarch_metacentric_height(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("KB", "BM", "KG"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = metacentric_height(a["KB"], a["BM"], a["KG"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: navalarch_righting_arm
# ---------------------------------------------------------------------------

_GZ_spec = ToolSpec(
    name="navalarch_righting_arm",
    description=(
        "Compute righting arm GZ at an angle of heel φ.\n"
        "\n"
        "Small-angle formula:\n"
        "  GZ_small = GM × sin(φ)\n"
        "\n"
        "Wall-sided correction (Moseley/Söding):\n"
        "  GZ_wall = (GM + ½·BM_T·tan²φ) × sin(φ)\n"
        "\n"
        "Flags non-positive GZ (no righting moment) in warnings.\n"
        "Returns GZ_small_angle_m, GZ_wall_sided_m, stable flag.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "GM": {"type": "number", "description": "Transverse metacentric height (m). May be negative."},
            "phi_deg": {"type": "number", "description": "Angle of heel (degrees). In [0, 90]."},
            "wall_sided_BM_T": {
                "type": "number",
                "description": (
                    "Transverse metacentric radius BM_T (m) for wall-sided correction. "
                    "Default 0.0 (small-angle only)."
                ),
            },
        },
        "required": ["GM", "phi_deg"],
    },
)


@register(_GZ_spec, write=False)
async def run_navalarch_righting_arm(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("GM") is None:
        return json.dumps({"ok": False, "reason": "GM is required"})
    if a.get("phi_deg") is None:
        return json.dumps({"ok": False, "reason": "phi_deg is required"})

    kwargs: dict = {}
    if "wall_sided_BM_T" in a:
        kwargs["wall_sided_BM_T"] = a["wall_sided_BM_T"]

    result = righting_arm_GZ(a["GM"], a["phi_deg"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: navalarch_tpc_mctc
# ---------------------------------------------------------------------------

_tpc_spec = ToolSpec(
    name="navalarch_tpc_mctc",
    description=(
        "Compute TPC (Tonnes Per Centimetre immersion) and MCT1cm "
        "(Moment to Change Trim 1 cm).\n"
        "\n"
        "  TPC     = Aw × ρ / (1000 × 100)         [t/cm]\n"
        "  IL_approx = Aw × L² / 12                [m⁴, rectangular approximation]\n"
        "  BML     = IL / ∇                         [m]\n"
        "  MCT1cm  = W × BML / (100 × L)           [t·m/cm]\n"
        "\n"
        "Returns TPC, MCT1cm_tm_per_cm, BML_approx_m.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Aw": {"type": "number", "description": "Waterplane area (m²). > 0."},
            "L": {"type": "number", "description": "Length between perpendiculars (m). > 0."},
            "displacement_t": {"type": "number", "description": "Displacement (tonnes). > 0."},
            "rho": {"type": "number", "description": "Water density (kg/m³). Default 1025."},
        },
        "required": ["Aw", "L", "displacement_t"],
    },
)


@register(_tpc_spec, write=False)
async def run_navalarch_tpc_mctc(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("Aw", "L", "displacement_t"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "rho" in a:
        kwargs["rho"] = a["rho"]

    result = tpc_mctc(a["Aw"], a["L"], a["displacement_t"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: navalarch_free_surface
# ---------------------------------------------------------------------------

_fs_spec = ToolSpec(
    name="navalarch_free_surface",
    description=(
        "Compute free-surface correction (FSC) to GM for a rectangular tank.\n"
        "\n"
        "  it  = l × b³ / 12           (second moment of free surface, m⁴)\n"
        "  FSC = (ρ_liquid / ρ_sw) × it / ∇   [m]\n"
        "\n"
        "The effective GM is reduced by FSC: GM_eff = GM − FSC.\n"
        "Returns FSC_m and free_surface_moment_tm.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "rho_liquid": {"type": "number", "description": "Tank liquid density (kg/m³). > 0."},
            "tank_length": {"type": "number", "description": "Length of free surface (m). > 0."},
            "tank_breadth": {"type": "number", "description": "Breadth of free surface (m). > 0."},
            "rho_sw": {"type": "number", "description": "Sea water density (kg/m³). Default 1025."},
            "displacement_t": {"type": "number", "description": "Ship displacement (tonnes). > 0."},
        },
        "required": ["rho_liquid", "tank_length", "tank_breadth", "displacement_t"],
    },
)


@register(_fs_spec, write=False)
async def run_navalarch_free_surface(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("rho_liquid", "tank_length", "tank_breadth", "displacement_t"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    rho_sw = a.get("rho_sw", 1025.0)
    result = free_surface_correction(
        a["rho_liquid"], a["tank_length"], a["tank_breadth"],
        rho_sw, a["displacement_t"],
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: navalarch_resistance
# ---------------------------------------------------------------------------

_resistance_spec = ToolSpec(
    name="navalarch_resistance",
    description=(
        "Estimate effective power using the Admiralty Coefficient method.\n"
        "\n"
        "  EHP = W^(2/3) × V³ / Ac    [hp]\n"
        "\n"
        "where W = displacement (tonnes), V = speed (knots), Ac = admiralty coefficient.\n"
        "Typical Ac ranges: cargo ships 350–500, tankers 700–1000, warships 150–250.\n"
        "\n"
        "Returns EHP_hp, EHP_kW.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "displacement_t": {"type": "number", "description": "Displacement (tonnes). > 0."},
            "V_knots": {"type": "number", "description": "Ship speed (knots). > 0."},
            "Ac": {
                "type": "number",
                "description": (
                    "Admiralty coefficient. > 0. "
                    "Typical: cargo 350–500, tankers 700–1000, warships 150–250."
                ),
            },
        },
        "required": ["displacement_t", "V_knots", "Ac"],
    },
)


@register(_resistance_spec, write=False)
async def run_navalarch_resistance(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("displacement_t", "V_knots", "Ac"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = resistance_admiralty(a["displacement_t"], a["V_knots"], a["Ac"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: navalarch_trim
# ---------------------------------------------------------------------------

_trim_spec = ToolSpec(
    name="navalarch_trim",
    description=(
        "Compute trim and change in draught forward and aft from a trimming moment.\n"
        "\n"
        "  trim_cm  = trimming_moment / MCTC\n"
        "  dT_aft   =  trim_cm × (L − LCF) / L\n"
        "  dT_fwd   = −trim_cm × LCF / L\n"
        "\n"
        "Sign convention: positive moment = trim by stern (stern goes deeper).\n"
        "Excessive trim (> 100 cm) is flagged in warnings — does not cause ok=False.\n"
        "\n"
        "Returns trim_cm, dT_aft_cm, dT_fwd_cm.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "trimming_moment_tm": {
                "type": "number",
                "description": "Trimming moment (tonne·metres). Positive = by stern. May be negative.",
            },
            "MCTC": {
                "type": "number",
                "description": "Moment to change trim 1 cm (tonne·metres per cm). > 0.",
            },
            "L": {"type": "number", "description": "Length between perpendiculars (m). > 0."},
            "LCF_fwd_AP": {
                "type": "number",
                "description": "Longitudinal centre of flotation from AP (m). In [0, L].",
            },
        },
        "required": ["trimming_moment_tm", "MCTC", "L", "LCF_fwd_AP"],
    },
)


@register(_trim_spec, write=False)
async def run_navalarch_trim(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("trimming_moment_tm", "MCTC", "L", "LCF_fwd_AP"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = trim_from_moment(
        a["trimming_moment_tm"], a["MCTC"], a["L"], a["LCF_fwd_AP"]
    )
    return ok_payload(result)
