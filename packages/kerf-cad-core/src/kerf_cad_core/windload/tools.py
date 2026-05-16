"""
kerf_cad_core.windload.tools — LLM tool wrappers for ASCE 7 wind loading.

Registers tools with the Kerf tool registry:

  wind_Kz                  — velocity pressure exposure coefficient Kz
  wind_Kzt                 — topographic factor Kzt
  wind_Ke                  — ground elevation factor Ke
  wind_qz                  — velocity pressure qz
  wind_G                   — gust-effect factor G (rigid structures)
  wind_Gf                  — gust-effect factor Gf (flexible structures)
  wind_mwfrs_wall          — MWFRS wall pressures
  wind_mwfrs_roof          — MWFRS roof pressures
  wind_cc_GCp              — components & cladding GCp coefficients
  wind_base_shear          — base shear and overturning moment
  wind_drift               — along-wind drift check

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
ASCE/SEI 7-22 — Minimum Design Loads and Associated Criteria for Buildings
and Other Structures (Chapters 26–27, 30)

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.windload.asce7 import (
    velocity_pressure_exposure_Kz,
    topographic_factor_Kzt,
    ground_elevation_factor_Ke,
    velocity_pressure_qz,
    gust_effect_factor_G,
    gust_effect_factor_Gf,
    mwfrs_wall_pressure,
    mwfrs_roof_pressure,
    components_cladding_GCp,
    base_shear_overturning,
    along_wind_drift,
)


# ---------------------------------------------------------------------------
# Tool: wind_Kz
# ---------------------------------------------------------------------------

_wind_Kz_spec = ToolSpec(
    name="wind_Kz",
    description=(
        "Compute the velocity pressure exposure coefficient Kz per ASCE 7-22 "
        "Table 26.10-1 for a given height and exposure category.\n"
        "\n"
        "Uses the power-law profile:\n"
        "  Kz = 2.01 × (z / zg)^(2/alpha)   for z >= z_min\n"
        "  Kz = 2.01 × (z_min / zg)^(2/alpha)  for z < z_min\n"
        "\n"
        "Exposure B: suburban/wooded terrain (alpha=7, zg=365.76 m).\n"
        "Exposure C: open terrain with scattered obstructions (alpha=9.5, zg=274.32 m).\n"
        "Exposure D: flat unobstructed areas, water surfaces (alpha=11.5, zg=213.36 m).\n"
        "\n"
        "Returns Kz (dimensionless). SI units (heights in metres)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "z": {
                "type": "number",
                "description": "Height above ground (m). Must be > 0.",
            },
            "exposure": {
                "type": "string",
                "enum": ["B", "C", "D"],
                "description": "Exposure category: 'B', 'C', or 'D'.",
            },
        },
        "required": ["z", "exposure"],
    },
)


@register(_wind_Kz_spec, write=False)
async def run_wind_Kz(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("z") is None:
        return json.dumps({"ok": False, "reason": "z is required"})
    if a.get("exposure") is None:
        return json.dumps({"ok": False, "reason": "exposure is required"})

    result = velocity_pressure_exposure_Kz(a["z"], a["exposure"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: wind_Kzt
# ---------------------------------------------------------------------------

_wind_Kzt_spec = ToolSpec(
    name="wind_Kzt",
    description=(
        "Compute the topographic factor Kzt per ASCE 7-22 Eq. 26.8-1.\n"
        "\n"
        "  Kzt = (1 + K1 · K2 · K3)²\n"
        "\n"
        "K1, K2, K3 are site-specific multipliers from ASCE 7-22 Figs. 26.8-1A/B/C.\n"
        "For flat terrain (no topographic feature): K1 = K2 = K3 = 0 → Kzt = 1.0.\n"
        "\n"
        "Returns Kzt (dimensionless, >= 1.0)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "K1": {
                "type": "number",
                "description": "Speed-up factor from ASCE 7-22 Fig. 26.8-1A. Must be >= 0.",
            },
            "K2": {
                "type": "number",
                "description": "Distance-from-crest factor from Fig. 26.8-1B. Must be >= 0.",
            },
            "K3": {
                "type": "number",
                "description": "Height factor from Fig. 26.8-1C. Must be >= 0.",
            },
        },
        "required": ["K1", "K2", "K3"],
    },
)


@register(_wind_Kzt_spec, write=False)
async def run_wind_Kzt(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("K1", "K2", "K3"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = topographic_factor_Kzt(a["K1"], a["K2"], a["K3"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: wind_Ke
# ---------------------------------------------------------------------------

_wind_Ke_spec = ToolSpec(
    name="wind_Ke",
    description=(
        "Compute the ground elevation factor Ke per ASCE 7-22 Eq. 26.9-1.\n"
        "\n"
        "  Ke = exp(-0.000119 × z_e)   (SI, z_e in metres)\n"
        "\n"
        "At sea level (z_e = 0), Ke = 1.0.\n"
        "At 1000 m elevation, Ke ≈ 0.887.\n"
        "\n"
        "Returns Ke (dimensionless, <= 1.0). SI units (elevation in metres)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "z_e_m": {
                "type": "number",
                "description": "Site ground elevation above sea level (m). Must be >= 0.",
            },
        },
        "required": ["z_e_m"],
    },
)


@register(_wind_Ke_spec, write=False)
async def run_wind_Ke(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("z_e_m") is None:
        return json.dumps({"ok": False, "reason": "z_e_m is required"})

    result = ground_elevation_factor_Ke(a["z_e_m"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: wind_qz
# ---------------------------------------------------------------------------

_wind_qz_spec = ToolSpec(
    name="wind_qz",
    description=(
        "Compute the design velocity pressure qz per ASCE 7-22 Eq. 26.10-1.\n"
        "\n"
        "SI:  qz = 0.613 · Kz · Kzt · Kd · Ke · V²   (Pa, V in m/s)\n"
        "US:  qz = 0.00256 · Kz · Kzt · Kd · Ke · V²  (psf, V in mph)\n"
        "\n"
        "Typical values: Kd = 0.85 (buildings), 0.95 (chimneys/tanks), 1.0 (all-direction).\n"
        "\n"
        "Returns qz in Pa (SI) or psf (US)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Kz": {
                "type": "number",
                "description": "Velocity pressure exposure coefficient (from wind_Kz). Must be > 0.",
            },
            "Kzt": {
                "type": "number",
                "description": "Topographic factor (from wind_Kzt; >= 1.0).",
            },
            "Kd": {
                "type": "number",
                "description": "Wind directionality factor (0.85–0.95 typical; must be in (0, 1]).",
            },
            "Ke": {
                "type": "number",
                "description": "Ground elevation factor (from wind_Ke; must be in (0, 1]).",
            },
            "V": {
                "type": "number",
                "description": "Basic wind speed (m/s for SI; mph for US). Must be > 0.",
            },
            "unit_system": {
                "type": "string",
                "enum": ["SI", "US"],
                "description": "Unit system: 'SI' (default, Pa, m/s) or 'US' (psf, mph).",
            },
        },
        "required": ["Kz", "Kzt", "Kd", "Ke", "V"],
    },
)


@register(_wind_qz_spec, write=False)
async def run_wind_qz(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("Kz", "Kzt", "Kd", "Ke", "V"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "unit_system" in a:
        kwargs["unit_system"] = a["unit_system"]

    result = velocity_pressure_qz(
        a["Kz"], a["Kzt"], a["Kd"], a["Ke"], a["V"], **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: wind_G
# ---------------------------------------------------------------------------

_wind_G_spec = ToolSpec(
    name="wind_G",
    description=(
        "Compute the gust-effect factor G for rigid structures per ASCE 7-22 §26.11.4.\n"
        "\n"
        "Simplified: G = 0.85 (when Iz is omitted).\n"
        "Detailed: G = 0.925 × (1 + 1.7·Iz·gQ·Q) / (1 + 1.7·gv·Iz)\n"
        "  where Q = 1/sqrt(1 + 0.63·((B+H)/Lz)^0.63), gQ = gv = 3.4.\n"
        "\n"
        "For flexible structures (n1 < 1 Hz or H > 60 m), use wind_Gf instead.\n"
        "\n"
        "Returns G (dimensionless, typically 0.85–1.0) and warnings list."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "exposure": {
                "type": "string",
                "enum": ["B", "C", "D"],
                "description": "Exposure category.",
            },
            "Iz": {
                "type": "number",
                "description": (
                    "Intensity of turbulence at mean roof height z_bar (dimensionless). "
                    "If omitted, simplified G = 0.85 is returned."
                ),
            },
            "Lz": {
                "type": "number",
                "description": "Integral length scale of turbulence at z_bar (m). Required if Iz provided.",
            },
            "Q_ratio": {
                "type": "number",
                "description": "(B + H) / Lz ratio. Required if Iz is provided.",
            },
            "flexible": {
                "type": "boolean",
                "description": "Set True to flag flexible-structure warning.",
            },
        },
        "required": ["exposure"],
    },
)


@register(_wind_G_spec, write=False)
async def run_wind_G(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("exposure") is None:
        return json.dumps({"ok": False, "reason": "exposure is required"})

    kwargs: dict = {}
    for field in ("Iz", "Lz", "Q_ratio", "flexible"):
        if field in a:
            kwargs[field] = a[field]

    result = gust_effect_factor_G(a["exposure"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: wind_Gf
# ---------------------------------------------------------------------------

_wind_Gf_spec = ToolSpec(
    name="wind_Gf",
    description=(
        "Compute the gust-effect factor Gf for flexible or dynamically sensitive "
        "structures per ASCE 7-22 §26.11.5.\n"
        "\n"
        "Applicable when n1 < 1 Hz (natural frequency) or H > 60 m.\n"
        "\n"
        "  Gf = 0.925 × (1 + 1.7·Iz·sqrt(gQ²Q² + gR²R²)) / (1 + 1.7·gv·Iz)\n"
        "\n"
        "Returns Gf, resonance factor R², spectral factors, and warnings list."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "n1": {
                "type": "number",
                "description": "Fundamental natural frequency (Hz). Must be > 0.",
            },
            "zbar": {
                "type": "number",
                "description": "Equivalent height (m), typically 0.6H. Must be > 0.",
            },
            "Iz": {
                "type": "number",
                "description": "Intensity of turbulence at zbar (dimensionless). Must be > 0.",
            },
            "Lz": {
                "type": "number",
                "description": "Integral length scale of turbulence at zbar (m). Must be > 0.",
            },
            "V": {
                "type": "number",
                "description": "Mean wind speed at zbar (m/s). Must be > 0.",
            },
            "B": {
                "type": "number",
                "description": "Building width perpendicular to wind (m). Must be > 0.",
            },
            "H": {
                "type": "number",
                "description": "Mean roof height (m). Must be > 0.",
            },
            "D": {
                "type": "number",
                "description": "Building depth along wind direction (m). Must be > 0.",
            },
            "damping_ratio": {
                "type": "number",
                "description": "Structural damping ratio β (fraction, default 0.02 = 2%).",
            },
        },
        "required": ["n1", "zbar", "Iz", "Lz", "V", "B", "H", "D"],
    },
)


@register(_wind_Gf_spec, write=False)
async def run_wind_Gf(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("n1", "zbar", "Iz", "Lz", "V", "B", "H", "D"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "damping_ratio" in a:
        kwargs["damping_ratio"] = a["damping_ratio"]

    result = gust_effect_factor_Gf(
        a["n1"], a["zbar"], a["Iz"], a["Lz"], a["V"],
        B=a["B"], H=a["H"], D=a["D"],
        **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: wind_mwfrs_wall
# ---------------------------------------------------------------------------

_wind_mwfrs_wall_spec = ToolSpec(
    name="wind_mwfrs_wall",
    description=(
        "Compute MWFRS external wall pressures per ASCE 7-22 §27.3.1.\n"
        "\n"
        "  p = q · G · Cp − qi · (±GCpi)\n"
        "\n"
        "Both ±GCpi cases are evaluated; the governing (maximum absolute) "
        "pressure is returned.\n"
        "\n"
        "Typical Cp values (ASCE 7-22 Table 27.3-1):\n"
        "  Windward wall: Cp = +0.8\n"
        "  Leeward wall:  Cp = -0.2 to -0.5 (depends on L/B ratio)\n"
        "  Side walls:    Cp = -0.7\n"
        "\n"
        "Returns p_pos, p_neg, p_critical (Pa or psf)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "qz": {
                "type": "number",
                "description": (
                    "Velocity pressure at height z (Pa or psf). "
                    "Use qz for windward; qh for leeward/side. Must be > 0."
                ),
            },
            "qi": {
                "type": "number",
                "description": "Internal pressure reference (qh, Pa or psf). Must be > 0.",
            },
            "G": {
                "type": "number",
                "description": "Gust-effect factor (dimensionless). Must be > 0.",
            },
            "Cp_windward": {
                "type": "number",
                "description": "External Cp for windward wall (+0.8 typical).",
            },
            "Cp_leeward": {
                "type": "number",
                "description": "External Cp for leeward wall (-0.2 to -0.5 typical, negative).",
            },
            "Cp_side": {
                "type": "number",
                "description": "External Cp for side walls (-0.7 typical, negative).",
            },
            "GCpi": {
                "type": "number",
                "description": (
                    "Internal pressure coefficient magnitude (Table 26.13-1): "
                    "0.18 (enclosed), 0.55 (partially enclosed), 0.0 (open). Must be >= 0."
                ),
            },
            "surface": {
                "type": "string",
                "enum": ["windward", "leeward", "side"],
                "description": "Surface to compute pressure for (default 'windward').",
            },
        },
        "required": ["qz", "qi", "G", "Cp_windward", "Cp_leeward", "Cp_side", "GCpi"],
    },
)


@register(_wind_mwfrs_wall_spec, write=False)
async def run_wind_mwfrs_wall(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("qz", "qi", "G", "Cp_windward", "Cp_leeward", "Cp_side", "GCpi"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "surface" in a:
        kwargs["surface"] = a["surface"]

    result = mwfrs_wall_pressure(
        a["qz"], a["qi"], a["G"],
        a["Cp_windward"], a["Cp_leeward"], a["Cp_side"],
        a["GCpi"],
        **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: wind_mwfrs_roof
# ---------------------------------------------------------------------------

_wind_mwfrs_roof_spec = ToolSpec(
    name="wind_mwfrs_roof",
    description=(
        "Compute MWFRS roof pressures per ASCE 7-22 §27.3.1.\n"
        "\n"
        "  p = qh · G · Cp − qi · (±GCpi)\n"
        "\n"
        "Both ±GCpi cases are evaluated; the critical pressure is returned.\n"
        "\n"
        "Typical flat-roof Cp values (ASCE 7-22 Table 27.3-1, h/L <= 0.5):\n"
        "  Windward roof: Cp = -0.9 to -0.18 (varies by zone)\n"
        "  Leeward roof:  Cp = -0.3 to -0.6\n"
        "\n"
        "Returns p_pos, p_neg, p_critical (Pa or psf)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "qh": {
                "type": "number",
                "description": "Velocity pressure at mean roof height h (Pa or psf). Must be > 0.",
            },
            "qi": {
                "type": "number",
                "description": "Internal pressure reference (qh, Pa or psf). Must be > 0.",
            },
            "G": {
                "type": "number",
                "description": "Gust-effect factor (dimensionless). Must be > 0.",
            },
            "Cp_roof": {
                "type": "number",
                "description": (
                    "External roof Cp (negative for flat/low-slope roofs). "
                    "Per ASCE 7-22 Table 27.3-1."
                ),
            },
            "GCpi": {
                "type": "number",
                "description": "Internal pressure coefficient magnitude. Must be >= 0.",
            },
        },
        "required": ["qh", "qi", "G", "Cp_roof", "GCpi"],
    },
)


@register(_wind_mwfrs_roof_spec, write=False)
async def run_wind_mwfrs_roof(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("qh", "qi", "G", "Cp_roof", "GCpi"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = mwfrs_roof_pressure(
        a["qh"], a["qi"], a["G"], a["Cp_roof"], a["GCpi"]
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: wind_cc_GCp
# ---------------------------------------------------------------------------

_wind_cc_GCp_spec = ToolSpec(
    name="wind_cc_GCp",
    description=(
        "Look up components & cladding GCp coefficients by zone and effective area "
        "per ASCE 7-22 Fig. 30.3-1 / 30.3-2 (low-rise buildings, h <= 18 m).\n"
        "\n"
        "Zone 1 = field, Zone 2 = edge, Zone 3 = corner.\n"
        "Component types: 'wall' or 'roof'.\n"
        "\n"
        "Design pressure: p = qh × (GCp - GCpi)\n"
        "\n"
        "Returns GCp_pos and GCp_neg (both dimensionless)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "zone": {
                "type": "integer",
                "enum": [1, 2, 3],
                "description": "Wind zone: 1 (field), 2 (edge), 3 (corner).",
            },
            "component_type": {
                "type": "string",
                "enum": ["wall", "roof"],
                "description": "Component type: 'wall' or 'roof'.",
            },
            "effective_area_m2": {
                "type": "number",
                "description": "Effective wind area of the component (m²). Must be > 0.",
            },
            "unit_system": {
                "type": "string",
                "enum": ["SI", "US"],
                "description": "Unit system (default 'SI'). GCp is dimensionless.",
            },
        },
        "required": ["zone", "component_type", "effective_area_m2"],
    },
)


@register(_wind_cc_GCp_spec, write=False)
async def run_wind_cc_GCp(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("zone", "component_type", "effective_area_m2"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "unit_system" in a:
        kwargs["unit_system"] = a["unit_system"]

    result = components_cladding_GCp(
        a["zone"], a["component_type"], a["effective_area_m2"], **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: wind_base_shear
# ---------------------------------------------------------------------------

_wind_base_shear_spec = ToolSpec(
    name="wind_base_shear",
    description=(
        "Compute base shear and overturning moment from MWFRS pressures.\n"
        "\n"
        "Sums pressure resultants over building height increments:\n"
        "  F_i = p_i × w_i × dz_i\n"
        "  V = ΣF_i\n"
        "  M_OT = Σ F_i × z_i  (z_i = centroid height of strip i)\n"
        "\n"
        "Returns base_shear (N or lb) and overturning_moment (N·m or ft·lb)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "pressures_by_height": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Design pressures at each level (Pa or psf). Length >= 1.",
            },
            "tributary_widths": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Tributary widths at each level (m or ft). Same length as pressures.",
            },
            "heights": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Height increments dz at each level (m or ft). Same length.",
            },
        },
        "required": ["pressures_by_height", "tributary_widths", "heights"],
    },
)


@register(_wind_base_shear_spec, write=False)
async def run_wind_base_shear(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("pressures_by_height", "tributary_widths", "heights"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = base_shear_overturning(
        a["pressures_by_height"], a["tributary_widths"], a["heights"]
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: wind_drift
# ---------------------------------------------------------------------------

_wind_drift_spec = ToolSpec(
    name="wind_drift",
    description=(
        "Simplified along-wind drift check per ASCE 7-22 §26.11.5 / Commentary.\n"
        "\n"
        "Computes allowable_drift = H / drift_limit_ratio and flags flexible "
        "structures (H > 60 m or estimated n1 < 1 Hz).\n"
        "\n"
        "Flexible-structure flag uses empirical n1 ≈ 75/H for steel frames.\n"
        "For accurate drift, combine with wind_Gf and modal analysis.\n"
        "\n"
        "Returns allowable_drift_m, flexible_flag, and warnings list."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "H": {
                "type": "number",
                "description": "Building total height (m). Must be > 0.",
            },
            "V": {
                "type": "number",
                "description": "Basic wind speed (m/s). Must be > 0.",
            },
            "exposure": {
                "type": "string",
                "enum": ["B", "C", "D"],
                "description": "Exposure category.",
            },
            "drift_limit_ratio": {
                "type": "number",
                "description": (
                    "Allowable drift ratio H/drift (default 500 = H/500 limit). "
                    "Must be > 0."
                ),
            },
        },
        "required": ["H", "V", "exposure"],
    },
)


@register(_wind_drift_spec, write=False)
async def run_wind_drift(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("H", "V", "exposure"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "drift_limit_ratio" in a:
        kwargs["drift_limit_ratio"] = a["drift_limit_ratio"]

    result = along_wind_drift(a["H"], a["V"], a["exposure"], **kwargs)
    return ok_payload(result)
