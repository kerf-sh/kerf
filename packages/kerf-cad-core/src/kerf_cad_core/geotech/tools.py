"""
kerf_cad_core.geotech.tools — LLM tool wrappers for geotechnical / foundation
engineering calculations.

Registers six tools with the Kerf tool registry:

  geotech_bearing_capacity        — Terzaghi/Meyerhof ultimate & allowable
                                    bearing capacity (strip/square/circular)
  geotech_settlement              — immediate & consolidation settlement
                                    (Cc/e0 one-dimensional method)
  geotech_lateral_earth_pressure  — Rankine & Coulomb Ka/Kp, resultant
                                    active/passive force (with surcharge &
                                    water table)
  geotech_retaining_wall          — overturning / sliding / bearing FS for
                                    gravity or cantilever retaining wall
  geotech_slope_stability         — infinite-slope simplified FS (dry,
                                    partial/full saturation)
  geotech_pile_capacity           — pile axial capacity (alpha-method skin
                                    friction + end bearing)

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
Das, B.M. "Principles of Geotechnical Engineering", 9th ed.
Bowles, J.E. "Foundation Analysis and Design", 5th ed.
Terzaghi (1943); Meyerhof (1951); Rankine (1857); Coulomb (1776).
API RP 2GEO — Geotechnical and Foundation Design Considerations.

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.geotech.foundation import (
    bearing_capacity,
    settlement,
    lateral_earth_pressure,
    retaining_wall_stability,
    slope_stability_infinite,
    pile_axial_capacity,
)


# ---------------------------------------------------------------------------
# Tool: geotech_bearing_capacity
# ---------------------------------------------------------------------------

_bearing_capacity_spec = ToolSpec(
    name="geotech_bearing_capacity",
    description=(
        "Compute the ultimate and allowable bearing capacity of a shallow "
        "foundation using Terzaghi (1943) bearing-capacity factors "
        "(Nc, Nq, Nγ) with shape factors for strip, square, or circular "
        "footings.\n"
        "\n"
        "  Strip:    q_ult = c·Nc + q·Nq + 0.5·γ·B·Nγ\n"
        "  Square:   q_ult = 1.3·c·Nc + q·Nq + 0.4·γ·B·Nγ\n"
        "  Circular: q_ult = 1.3·c·Nc + q·Nq + 0.3·γ·B·Nγ\n"
        "\n"
        "q_allow = q_ult / FS.  Flags FS < 3.0 and soft/liquefaction-prone "
        "soils in warnings.\n"
        "\n"
        "Returns Nc, Nq, Ngamma, q_ult_kPa, q_allow_kPa, warnings.\n"
        "Errors: {ok:false, reason} — never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "c": {
                "type": "number",
                "description": "Cohesion (kPa). Must be >= 0.",
            },
            "phi_deg": {
                "type": "number",
                "description": "Friction angle (°). Must be in [0, 45].",
            },
            "gamma": {
                "type": "number",
                "description": "Unit weight of soil (kN/m³). Must be > 0.",
            },
            "Df": {
                "type": "number",
                "description": "Foundation depth (m). Must be >= 0.",
            },
            "B": {
                "type": "number",
                "description": "Foundation width (m). Must be > 0.",
            },
            "foundation_type": {
                "type": "string",
                "enum": ["strip", "square", "circular"],
                "description": (
                    "Footing shape: 'strip' (default), 'square', or 'circular'."
                ),
            },
            "FS": {
                "type": "number",
                "description": (
                    "Factor of safety on q_ult (default 3.0). Must be > 0. "
                    "Typical minimum: 3.0 for bearing capacity."
                ),
            },
            "surcharge": {
                "type": "number",
                "description": (
                    "Additional surcharge pressure at foundation level (kPa). "
                    "Default 0.0. Must be >= 0."
                ),
            },
        },
        "required": ["c", "phi_deg", "gamma", "Df", "B"],
    },
)


@register(_bearing_capacity_spec, write=False)
async def run_bearing_capacity(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("c", "phi_deg", "gamma", "Df", "B"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "foundation_type" in a:
        kwargs["foundation_type"] = a["foundation_type"]
    if "FS" in a:
        kwargs["FS"] = a["FS"]
    if "surcharge" in a:
        kwargs["surcharge"] = a["surcharge"]

    result = bearing_capacity(a["c"], a["phi_deg"], a["gamma"], a["Df"], a["B"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: geotech_settlement
# ---------------------------------------------------------------------------

_settlement_spec = ToolSpec(
    name="geotech_settlement",
    description=(
        "Compute foundation settlement.\n"
        "\n"
        "For 'consolidation' (default): primary consolidation using the "
        "Terzaghi 1D compression equation:\n"
        "\n"
        "  Sc = (Cc / (1 + e0)) × H × log10(σ'v / σ'v0)\n"
        "\n"
        "For 'immediate': elastic immediate settlement via simplified "
        "Boussinesq: Si ≈ q·B·(1−ν²)/Es  where sigma_v=q (kPa), "
        "Cc=Es (kPa), e0=ν (Poisson ratio), H=B (footing width, m).\n"
        "\n"
        "Flags high Cc values (soft/organic clay) and excessive settlements "
        "in warnings.\n"
        "\n"
        "Returns settlement_m, settlement_mm, warnings.\n"
        "Errors: {ok:false, reason} — never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "sigma_v": {
                "type": "number",
                "description": (
                    "Final effective vertical stress at mid-layer (kPa). > 0. "
                    "For immediate settlement: net bearing pressure q (kPa)."
                ),
            },
            "Cc": {
                "type": "number",
                "description": (
                    "Compression index Cc. > 0. "
                    "For immediate settlement: elastic modulus Es (kPa)."
                ),
            },
            "e0": {
                "type": "number",
                "description": (
                    "Initial void ratio e0. > 0. "
                    "For immediate settlement: Poisson ratio ν (0 < ν < 0.5)."
                ),
            },
            "H": {
                "type": "number",
                "description": (
                    "Thickness of compressible layer (m). > 0. "
                    "For immediate settlement: footing width B (m)."
                ),
            },
            "sigma_v0": {
                "type": "number",
                "description": (
                    "Initial effective vertical stress (kPa). > 0. "
                    "If omitted, defaults to 0.5 × sigma_v."
                ),
            },
            "settlement_type": {
                "type": "string",
                "enum": ["consolidation", "immediate"],
                "description": (
                    "Settlement type: 'consolidation' (default, Terzaghi 1D) "
                    "or 'immediate' (elastic Boussinesq approximation)."
                ),
            },
        },
        "required": ["sigma_v", "Cc", "e0", "H"],
    },
)


@register(_settlement_spec, write=False)
async def run_settlement(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("sigma_v", "Cc", "e0", "H"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "sigma_v0" in a:
        kwargs["sigma_v0"] = a["sigma_v0"]
    if "settlement_type" in a:
        kwargs["settlement_type"] = a["settlement_type"]

    result = settlement(a["sigma_v"], a["Cc"], a["e0"], a["H"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: geotech_lateral_earth_pressure
# ---------------------------------------------------------------------------

_lateral_earth_pressure_spec = ToolSpec(
    name="geotech_lateral_earth_pressure",
    description=(
        "Compute Rankine or Coulomb lateral earth pressure coefficients Ka, Kp "
        "and the resultant active (Pa) and passive (Pp) forces per unit wall "
        "length, including surcharge and water-table effects.\n"
        "\n"
        "Rankine (1857): vertical wall, horizontal backfill.\n"
        "  Ka = tan²(45 − φ/2)\n"
        "  Kp = tan²(45 + φ/2)\n"
        "\n"
        "Coulomb (1776): accounts for wall friction δ; Kp uses Rankine "
        "(conservative).\n"
        "\n"
        "Returns Ka, Kp, Pa_kN_m, Pp_kN_m, Pa_z_m, Pp_z_m, warnings.\n"
        "Errors: {ok:false, reason} — never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "gamma": {
                "type": "number",
                "description": "Unit weight of soil (kN/m³). > 0.",
            },
            "H": {
                "type": "number",
                "description": "Retained wall height (m). > 0.",
            },
            "phi_deg": {
                "type": "number",
                "description": "Internal friction angle (°). In [0, 45].",
            },
            "method": {
                "type": "string",
                "enum": ["rankine", "coulomb"],
                "description": "Method: 'rankine' (default) or 'coulomb'.",
            },
            "c": {
                "type": "number",
                "description": "Cohesion (kPa). Default 0. >= 0.",
            },
            "delta_deg": {
                "type": "number",
                "description": (
                    "Wall friction angle δ (°). Used for Coulomb only. "
                    "Default 0. >= 0."
                ),
            },
            "surcharge": {
                "type": "number",
                "description": "Uniform surcharge on backfill surface (kPa). Default 0. >= 0.",
            },
            "hw": {
                "type": "number",
                "description": (
                    "Depth of water table from top of wall (m). "
                    "0 = fully dry (default). >= 0."
                ),
            },
        },
        "required": ["gamma", "H", "phi_deg"],
    },
)


@register(_lateral_earth_pressure_spec, write=False)
async def run_lateral_earth_pressure(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("gamma", "H", "phi_deg"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("method", "c", "delta_deg", "surcharge", "hw"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = lateral_earth_pressure(a["gamma"], a["H"], a["phi_deg"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: geotech_retaining_wall
# ---------------------------------------------------------------------------

_retaining_wall_spec = ToolSpec(
    name="geotech_retaining_wall",
    description=(
        "Check stability of a gravity or cantilever retaining wall against "
        "overturning, sliding, and bearing capacity failure.\n"
        "\n"
        "Computes:\n"
        "  FS_overturning — stabilising moment / overturning moment\n"
        "  FS_sliding     — resisting force / driving force\n"
        "  FS_bearing     — q_ult / q_applied (Terzaghi strip)\n"
        "\n"
        "Flags checks below required FS thresholds and eccentricity "
        "outside the middle-third (kern) in warnings.\n"
        "\n"
        "Returns FS values, ok booleans, eccentricity, warnings.\n"
        "Errors: {ok:false, reason} — never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Fa": {
                "type": "number",
                "description": "Active resultant force per unit length (kN/m). >= 0.",
            },
            "Fp": {
                "type": "number",
                "description": "Passive resultant force per unit length (kN/m). >= 0.",
            },
            "W_wall": {
                "type": "number",
                "description": (
                    "Total vertical weight of wall + retained soil per unit "
                    "length (kN/m). > 0."
                ),
            },
            "x_W": {
                "type": "number",
                "description": (
                    "Horizontal distance from toe to resultant vertical force (m). > 0."
                ),
            },
            "B_base": {
                "type": "number",
                "description": "Base width of wall (m). > 0.",
            },
            "Df": {
                "type": "number",
                "description": "Foundation depth (m). >= 0.",
            },
            "c": {
                "type": "number",
                "description": "Cohesion at base (kPa). >= 0.",
            },
            "phi_deg": {
                "type": "number",
                "description": "Friction angle at base (°). In [0, 45].",
            },
            "gamma": {
                "type": "number",
                "description": "Unit weight of soil (kN/m³). > 0.",
            },
            "FS_req_ot": {
                "type": "number",
                "description": "Required FS overturning (default 2.0). > 0.",
            },
            "FS_req_sl": {
                "type": "number",
                "description": "Required FS sliding (default 1.5). > 0.",
            },
            "FS_req_bc": {
                "type": "number",
                "description": "Required FS bearing (default 3.0). > 0.",
            },
        },
        "required": ["Fa", "Fp", "W_wall", "x_W", "B_base", "Df", "c", "phi_deg", "gamma"],
    },
)


@register(_retaining_wall_spec, write=False)
async def run_retaining_wall(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    required = ("Fa", "Fp", "W_wall", "x_W", "B_base", "Df", "c", "phi_deg", "gamma")
    for field in required:
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("FS_req_ot", "FS_req_sl", "FS_req_bc"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = retaining_wall_stability(
        a["Fa"], a["Fp"], a["W_wall"], a["x_W"],
        a["B_base"], a["Df"], a["c"], a["phi_deg"], a["gamma"],
        **kwargs,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: geotech_slope_stability
# ---------------------------------------------------------------------------

_slope_stability_spec = ToolSpec(
    name="geotech_slope_stability",
    description=(
        "Simplified infinite-slope factor of safety for a cohesive or "
        "frictional soil slope.\n"
        "\n"
        "Dry (hw_ratio=0):\n"
        "  FS = c/(γ·H·sin β·cos β) + tan φ / tan β\n"
        "\n"
        "Partially saturated (m = hw_ratio = hw/H):\n"
        "  FS = c/(γ·H·sin β·cos β) + (1 − m·γw/γ)·tan φ / tan β\n"
        "\n"
        "Flags FS < required, liquefaction-prone soils "
        "(phi_deg < 5, c < 1 kPa), and near-saturated conditions.\n"
        "\n"
        "Returns FS, adequate (bool), warnings.\n"
        "Errors: {ok:false, reason} — never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "gamma": {
                "type": "number",
                "description": "Unit weight of soil (kN/m³). > 0.",
            },
            "c": {
                "type": "number",
                "description": "Cohesion (kPa). >= 0.",
            },
            "phi_deg": {
                "type": "number",
                "description": "Internal friction angle (°). In [0, 45].",
            },
            "H": {
                "type": "number",
                "description": "Depth to failure plane (m). > 0.",
            },
            "beta_deg": {
                "type": "number",
                "description": "Slope angle (°). Must be in (0, 90).",
            },
            "hw_ratio": {
                "type": "number",
                "description": (
                    "hw/H — water table depth ratio. 0.0 = dry (default); "
                    "1.0 = fully saturated. Must be in [0, 1]."
                ),
            },
            "FS_req": {
                "type": "number",
                "description": "Required factor of safety (default 1.5). > 0.",
            },
        },
        "required": ["gamma", "c", "phi_deg", "H", "beta_deg"],
    },
)


@register(_slope_stability_spec, write=False)
async def run_slope_stability(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("gamma", "c", "phi_deg", "H", "beta_deg"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("hw_ratio", "FS_req"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = slope_stability_infinite(
        a["gamma"], a["c"], a["phi_deg"], a["H"], a["beta_deg"], **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: geotech_pile_capacity
# ---------------------------------------------------------------------------

_pile_capacity_spec = ToolSpec(
    name="geotech_pile_capacity",
    description=(
        "Compute axial pile capacity using the alpha-method (skin friction) "
        "and end-bearing.\n"
        "\n"
        "  Qs = α × fs × perimeter × L    [skin friction, kN]\n"
        "  Qp = qp × A_tip                 [end bearing, kN]\n"
        "  Q_ult = Qs + Qp\n"
        "  Q_allow = Q_ult / FS\n"
        "\n"
        "References: API RP 2GEO; Tomlinson α-method.\n"
        "Flags low FS, unusually low α, and end-bearing dominance in warnings.\n"
        "\n"
        "Returns Qs_kN, Qp_kN, Q_ult_kN, Q_allow_kN, warnings.\n"
        "Errors: {ok:false, reason} — never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "perimeter": {
                "type": "number",
                "description": "Pile perimeter (m). > 0.",
            },
            "area_tip": {
                "type": "number",
                "description": "Pile tip cross-sectional area (m²). > 0.",
            },
            "unit_skin_friction": {
                "type": "number",
                "description": (
                    "Average unit skin friction fs (kPa), typically = su "
                    "(undrained shear strength). >= 0."
                ),
            },
            "unit_end_bearing": {
                "type": "number",
                "description": (
                    "Unit end-bearing capacity qp (kPa). "
                    "Typical: Nc × cu ≈ 9 × su at pile tip. >= 0."
                ),
            },
            "pile_length": {
                "type": "number",
                "description": "Total pile length (m). > 0.",
            },
            "alpha": {
                "type": "number",
                "description": (
                    "Adhesion factor α (dimensionless). "
                    "Range 0.4–0.8 for driven piles in soft clay (default 1.0). "
                    "Must be in (0, 1]."
                ),
            },
            "FS": {
                "type": "number",
                "description": (
                    "Factor of safety on Q_ult (default 3.0). "
                    "Typical minimum: 2.5–3.0. > 0."
                ),
            },
        },
        "required": [
            "perimeter", "area_tip", "unit_skin_friction",
            "unit_end_bearing", "pile_length",
        ],
    },
)


@register(_pile_capacity_spec, write=False)
async def run_pile_capacity(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    required = ("perimeter", "area_tip", "unit_skin_friction",
                 "unit_end_bearing", "pile_length")
    for field in required:
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("alpha", "FS"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = pile_axial_capacity(
        a["perimeter"], a["area_tip"],
        a["unit_skin_friction"], a["unit_end_bearing"],
        a["pile_length"], **kwargs,
    )
    return ok_payload(result)
