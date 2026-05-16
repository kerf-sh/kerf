"""
kerf_cad_core.pavement.tools — LLM tool wrappers for pavement design.

Registers tools with the Kerf tool registry:

  pavement_flexible_sn        — AASHTO '93 structural number SN (flexible)
  pavement_flexible_layers    — Layer thicknesses from SN + layer coefficients
  pavement_esals              — Design-period ESALs from traffic inputs
  pavement_esal_growth        — Geometric traffic growth factor
  pavement_lef                — Load equivalency factor (AASHTO power-law)
  pavement_cbr_to_mr          — CBR → resilient modulus MR (psi)
  pavement_cbr_to_k           — CBR → modulus of subgrade reaction k (pci)
  pavement_boussinesq         — Boussinesq vertical stress under circular load
  pavement_rigid_thickness    — AASHTO '93 rigid slab thickness (iterative)
  pavement_joint_spacing      — Contraction joint spacing
  pavement_dowel_bar          — Recommended dowel bar size
  pavement_frost_depth        — Frost penetration depth (Stefan simplified)
  pavement_overlay_sn         — Overlay thickness from SN-deficiency method
  pavement_asphalt_quantity   — Asphalt mix quantity

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
AASHTO Guide for Design of Pavement Structures, 1993
Huang, Y.H. (2004). Pavement Analysis and Design, 2nd ed.

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.pavement.design import (
    aashto93_flexible_sn,
    aashto93_flexible_layers,
    esals_design,
    esal_growth_factor,
    load_equivalency_factor,
    cbr_to_mr,
    cbr_to_k,
    boussinesq_stress,
    aashto93_rigid_thickness,
    joint_spacing,
    dowel_bar_size,
    frost_penetration_depth,
    overlay_thickness_sn,
    asphalt_quantity,
)


# ---------------------------------------------------------------------------
# Tool: pavement_flexible_sn
# ---------------------------------------------------------------------------

_flex_sn_spec = ToolSpec(
    name="pavement_flexible_sn",
    description=(
        "Compute the required structural number SN for flexible (asphalt) "
        "pavement using the AASHTO '93 design equation.\n"
        "\n"
        "Solves iteratively for SN given design traffic W18 (ESALs), "
        "reliability ZR, standard deviation S0, serviceability loss ΔPSI, "
        "and subgrade resilient modulus MR (psi).\n"
        "\n"
        "Returns SN (dimensionless).  Use pavement_flexible_layers to "
        "convert SN into layer thicknesses.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "W18": {
                "type": "number",
                "description": "Design traffic in ESALs (18-kip equivalent single-axle loads). Must be > 0.",
            },
            "ZR": {
                "type": "number",
                "description": (
                    "Standard normal deviate for reliability. "
                    "R=50%→0.000; R=90%→-1.282; R=95%→-1.645; R=99%→-2.327."
                ),
            },
            "S0": {
                "type": "number",
                "description": "Overall standard deviation for flexible pavement. Typical: 0.45. Must be > 0.",
            },
            "DPSI": {
                "type": "number",
                "description": (
                    "Design serviceability loss = PSI_initial - PSI_terminal. "
                    "Typical: 4.2 - 2.5 = 1.7 (major roads). Must be in (0, 4.2)."
                ),
            },
            "MR": {
                "type": "number",
                "description": "Effective subgrade resilient modulus (psi). Typical: 3000–30000 psi. Must be > 0.",
            },
        },
        "required": ["W18", "ZR", "S0", "DPSI", "MR"],
    },
)


@register(_flex_sn_spec, write=False)
async def run_pavement_flexible_sn(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("W18", "ZR", "S0", "DPSI", "MR"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = aashto93_flexible_sn(a["W18"], a["ZR"], a["S0"], a["DPSI"], a["MR"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pavement_flexible_layers
# ---------------------------------------------------------------------------

_flex_layers_spec = ToolSpec(
    name="pavement_flexible_layers",
    description=(
        "Compute required layer thicknesses for flexible (asphalt) pavement "
        "from a structural number SN and layer coefficients.\n"
        "\n"
        "Uses the AASHTO '93 stage-solve method: "
        "D_i = remaining SN / (a_i × m_i), rounded up to 0.5 in., "
        "subject to AASHTO minimum thickness per layer type.\n"
        "\n"
        "Each layer dict requires:\n"
        "  'a'    : layer coefficient (1/in.)\n"
        "  'm'    : drainage coefficient (default 1.0)\n"
        "  'type' : 'asphalt' | 'base' | 'subbase' | 'other'\n"
        "  'name' : label (optional)\n"
        "\n"
        "Returns per-layer D_in (inches) and SN_contrib.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "SN": {
                "type": "number",
                "description": "Required structural number (from pavement_flexible_sn). Must be > 0.",
            },
            "layers": {
                "type": "array",
                "description": "Ordered list of layers (surface to bottom). Each item is a dict with 'a', optional 'm', 'type', 'name'.",
                "items": {
                    "type": "object",
                    "properties": {
                        "a":    {"type": "number", "description": "Layer coefficient a_i (1/in.). E.g. HMA=0.44, crushed stone base=0.14."},
                        "m":    {"type": "number", "description": "Drainage coefficient m_i (default 1.0). Typical: 0.7–1.4."},
                        "type": {"type": "string", "enum": ["asphalt", "base", "subbase", "other"]},
                        "name": {"type": "string"},
                    },
                    "required": ["a"],
                },
            },
        },
        "required": ["SN", "layers"],
    },
)


@register(_flex_layers_spec, write=False)
async def run_pavement_flexible_layers(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("SN") is None:
        return json.dumps({"ok": False, "reason": "SN is required"})
    if a.get("layers") is None:
        return json.dumps({"ok": False, "reason": "layers is required"})

    result = aashto93_flexible_layers(a["SN"], a["layers"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pavement_esals
# ---------------------------------------------------------------------------

_esals_spec = ToolSpec(
    name="pavement_esals",
    description=(
        "Compute design-period ESALs from traffic inputs.\n"
        "\n"
        "W18 = ADT × truck_factor × lane_dist × dir_dist × 365 × G\n"
        "\n"
        "where G is the compound traffic growth factor over the design period.\n"
        "\n"
        "Returns W18 (ESALs), annual_ESAL, and growth_factor.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "ADT": {
                "type": "number",
                "description": "Average Daily Traffic (vehicles/day, both directions). Must be > 0.",
            },
            "truck_factor": {
                "type": "number",
                "description": "Average ESALs per truck from axle load spectra. Typical: 0.1–5.0. Must be > 0.",
            },
            "lane_dist": {
                "type": "number",
                "description": "Lane distribution factor (fraction in design lane). Typical: 0.45–1.0.",
            },
            "dir_dist": {
                "type": "number",
                "description": "Directional distribution factor. Typically 0.5 (equal split).",
            },
            "design_years": {
                "type": "number",
                "description": "Design period (years). Must be > 0.",
            },
            "growth_rate": {
                "type": "number",
                "description": "Annual traffic growth rate as decimal (e.g. 0.03 = 3%). >= 0.",
            },
        },
        "required": ["ADT", "truck_factor", "lane_dist", "dir_dist", "design_years", "growth_rate"],
    },
)


@register(_esals_spec, write=False)
async def run_pavement_esals(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("ADT", "truck_factor", "lane_dist", "dir_dist", "design_years", "growth_rate"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = esals_design(
        a["ADT"], a["truck_factor"], a["lane_dist"],
        a["dir_dist"], a["design_years"], a["growth_rate"],
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pavement_esal_growth
# ---------------------------------------------------------------------------

_esal_growth_spec = ToolSpec(
    name="pavement_esal_growth",
    description=(
        "Compute the geometric (compound) traffic growth factor G for ESAL "
        "accumulation over a design period.\n"
        "\n"
        "G = [(1+r)^n - 1] / r  for r > 0,  G = n  for r = 0.\n"
        "\n"
        "Returns growth_factor G (years).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "growth_rate": {
                "type": "number",
                "description": "Annual traffic growth rate as decimal (e.g. 0.03 = 3%). >= 0.",
            },
            "design_years": {
                "type": "number",
                "description": "Design period in years. Must be > 0.",
            },
        },
        "required": ["growth_rate", "design_years"],
    },
)


@register(_esal_growth_spec, write=False)
async def run_pavement_esal_growth(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("growth_rate", "design_years"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = esal_growth_factor(a["growth_rate"], a["design_years"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pavement_lef
# ---------------------------------------------------------------------------

_lef_spec = ToolSpec(
    name="pavement_lef",
    description=(
        "Compute the Load Equivalency Factor (LEF) for converting an axle "
        "load to 18-kip (80-kN) ESALs via the AASHTO power-law.\n"
        "\n"
        "LEF = (axle_load / standard_axle)^4.0\n"
        "\n"
        "Standard axles: single=80 kN, tandem=142 kN, tridem=178 kN.\n"
        "\n"
        "Returns LEF (dimensionless).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "axle_load_kN": {
                "type": "number",
                "description": "Axle load (kN). Must be > 0.",
            },
            "axle_type": {
                "type": "string",
                "enum": ["single", "tandem", "tridem"],
                "description": "Axle configuration. Default: 'single'.",
            },
        },
        "required": ["axle_load_kN"],
    },
)


@register(_lef_spec, write=False)
async def run_pavement_lef(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("axle_load_kN") is None:
        return json.dumps({"ok": False, "reason": "axle_load_kN is required"})

    kwargs: dict = {}
    if "axle_type" in a:
        kwargs["axle_type"] = a["axle_type"]

    result = load_equivalency_factor(a["axle_load_kN"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pavement_cbr_to_mr
# ---------------------------------------------------------------------------

_cbr_mr_spec = ToolSpec(
    name="pavement_cbr_to_mr",
    description=(
        "Convert subgrade CBR (%) to resilient modulus MR (psi) using the "
        "AASHTO '93 correlation: MR = 1500 × CBR.\n"
        "\n"
        "Returns MR_psi.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "CBR": {
                "type": "number",
                "description": "California Bearing Ratio (percent). Must be in (0, 100].",
            },
        },
        "required": ["CBR"],
    },
)


@register(_cbr_mr_spec, write=False)
async def run_pavement_cbr_to_mr(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("CBR") is None:
        return json.dumps({"ok": False, "reason": "CBR is required"})

    result = cbr_to_mr(a["CBR"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pavement_cbr_to_k
# ---------------------------------------------------------------------------

_cbr_k_spec = ToolSpec(
    name="pavement_cbr_to_k",
    description=(
        "Convert subgrade CBR (%) to modulus of subgrade reaction k (pci) "
        "for rigid pavement design, using the Huang power-law correlation: "
        "k = 26.3 × CBR^0.45.\n"
        "\n"
        "Returns k_pci.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "CBR": {
                "type": "number",
                "description": "California Bearing Ratio (percent). Must be in (0, 100].",
            },
        },
        "required": ["CBR"],
    },
)


@register(_cbr_k_spec, write=False)
async def run_pavement_cbr_to_k(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("CBR") is None:
        return json.dumps({"ok": False, "reason": "CBR is required"})

    result = cbr_to_k(a["CBR"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pavement_boussinesq
# ---------------------------------------------------------------------------

_boussinesq_spec = ToolSpec(
    name="pavement_boussinesq",
    description=(
        "Compute vertical stress σ_z under the centre of a uniformly loaded "
        "circular area (Boussinesq elastic half-space).\n"
        "\n"
        "σ_z = q × [1 - z³ / (a² + z²)^(3/2)]\n"
        "\n"
        "Returns sigma_z_Pa and stress_ratio (σ_z/q).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "q": {
                "type": "number",
                "description": "Contact pressure (Pa). Must be > 0.",
            },
            "a": {
                "type": "number",
                "description": "Radius of loaded area (m). Must be > 0.",
            },
            "z": {
                "type": "number",
                "description": "Depth below surface (m). Must be > 0.",
            },
        },
        "required": ["q", "a", "z"],
    },
)


@register(_boussinesq_spec, write=False)
async def run_pavement_boussinesq(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("q", "a", "z"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = boussinesq_stress(a["q"], a["a"], a["z"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pavement_rigid_thickness
# ---------------------------------------------------------------------------

_rigid_spec = ToolSpec(
    name="pavement_rigid_thickness",
    description=(
        "Compute required PCC slab thickness D for rigid pavement using the "
        "iterative AASHTO '93 equation.\n"
        "\n"
        "Solves for D (inches) given W18, ZR, S0, ΔPSI, PCC modulus of rupture "
        "Sc (psi), drainage Cd, load-transfer J, PCC modulus Ec (psi), and "
        "modulus of subgrade reaction k (pci).\n"
        "\n"
        "Returns D_in (rounded up to 0.5 in.).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "W18":  {"type": "number", "description": "Design ESALs. Must be > 0."},
            "ZR":   {"type": "number", "description": "Standard normal deviate for reliability. Finite."},
            "S0":   {"type": "number", "description": "Overall standard deviation for rigid pavement. Typical: 0.35. > 0."},
            "DPSI": {"type": "number", "description": "Serviceability loss (PSI_initial=4.5 for rigid). Typical: 4.5-2.5=2.0. Must be in (0, 4.5)."},
            "Sc":   {"type": "number", "description": "PCC modulus of rupture (psi). Typical: 600–700 psi. Must be > 0."},
            "Cd":   {"type": "number", "description": "Drainage coefficient. Typical: 0.7–1.25. Must be > 0."},
            "J":    {"type": "number", "description": "Load transfer coefficient. Typical: 3.2 (dowelled), 3.8–4.4 (undowelled). Must be > 0."},
            "Ec":   {"type": "number", "description": "PCC elastic modulus (psi). Typical: 4e6 psi. Must be > 0."},
            "k":    {"type": "number", "description": "Modulus of subgrade reaction (pci). Use pavement_cbr_to_k(). Must be > 0."},
            "pt":   {"type": "number", "description": "Terminal serviceability index. Default: 2.5. Must be in [1.5, 3.5]."},
        },
        "required": ["W18", "ZR", "S0", "DPSI", "Sc", "Cd", "J", "Ec", "k"],
    },
)


@register(_rigid_spec, write=False)
async def run_pavement_rigid_thickness(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("W18", "ZR", "S0", "DPSI", "Sc", "Cd", "J", "Ec", "k"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "pt" in a:
        kwargs["pt"] = a["pt"]

    result = aashto93_rigid_thickness(
        a["W18"], a["ZR"], a["S0"], a["DPSI"],
        a["Sc"], a["Cd"], a["J"], a["Ec"], a["k"],
        **kwargs,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pavement_joint_spacing
# ---------------------------------------------------------------------------

_joint_spec = ToolSpec(
    name="pavement_joint_spacing",
    description=(
        "Compute contraction joint spacing for a rigid pavement slab based "
        "on thermal strain limit.\n"
        "\n"
        "L_joint = allow_strain / (coeff_thermal × delta_temp)\n"
        "\n"
        "Returns L_joint_m and L_over_h ratio.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "h_slab_mm": {
                "type": "number",
                "description": "Slab thickness (mm). Must be > 0.",
            },
            "coeff_thermal": {
                "type": "number",
                "description": "PCC thermal expansion coefficient (1/°C). Default: 10e-6.",
            },
            "delta_temp": {
                "type": "number",
                "description": "Temperature differential top-to-bottom (°C). Default: 30.",
            },
            "allow_strain": {
                "type": "number",
                "description": "Allowable joint opening strain. Default: 2e-4.",
            },
        },
        "required": ["h_slab_mm"],
    },
)


@register(_joint_spec, write=False)
async def run_pavement_joint_spacing(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("h_slab_mm") is None:
        return json.dumps({"ok": False, "reason": "h_slab_mm is required"})

    kwargs: dict = {}
    for opt in ("coeff_thermal", "delta_temp", "allow_strain"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = joint_spacing(a["h_slab_mm"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pavement_dowel_bar
# ---------------------------------------------------------------------------

_dowel_spec = ToolSpec(
    name="pavement_dowel_bar",
    description=(
        "Select the recommended dowel bar diameter and spacing for rigid "
        "pavement transverse joints.\n"
        "\n"
        "Follows AASHTO rule-of-thumb: d_dowel ≈ h_slab / 8, "
        "rounded up to the nearest standard bar diameter.\n"
        "\n"
        "Returns dowel_diameter_mm, dowel_spacing_mm (300 mm), "
        "and dowel_length_mm (450 mm).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "h_slab_mm": {
                "type": "number",
                "description": "Slab thickness (mm). Must be > 0.",
            },
        },
        "required": ["h_slab_mm"],
    },
)


@register(_dowel_spec, write=False)
async def run_pavement_dowel_bar(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("h_slab_mm") is None:
        return json.dumps({"ok": False, "reason": "h_slab_mm is required"})

    result = dowel_bar_size(a["h_slab_mm"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pavement_frost_depth
# ---------------------------------------------------------------------------

_frost_spec = ToolSpec(
    name="pavement_frost_depth",
    description=(
        "Estimate frost penetration depth using the simplified Stefan "
        "(modified Berggren) equation.\n"
        "\n"
        "z = sqrt(2 × k_soil × FI × 86400 / L_soil)\n"
        "\n"
        "Returns z_frost_m.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "freezing_index_degC_days": {
                "type": "number",
                "description": "Air freezing index (°C·days). Typical: 100–3000. Must be > 0.",
            },
            "k_soil": {
                "type": "number",
                "description": "Thermal conductivity of frozen soil (W/m·K). Typical: 0.5–2.5. Must be > 0.",
            },
            "L_soil": {
                "type": "number",
                "description": "Volumetric latent heat of soil (J/m³). Typical: 40e6–120e6 J/m³. Must be > 0.",
            },
        },
        "required": ["freezing_index_degC_days", "k_soil", "L_soil"],
    },
)


@register(_frost_spec, write=False)
async def run_pavement_frost_depth(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("freezing_index_degC_days", "k_soil", "L_soil"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = frost_penetration_depth(
        a["freezing_index_degC_days"], a["k_soil"], a["L_soil"]
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pavement_overlay_sn
# ---------------------------------------------------------------------------

_overlay_spec = ToolSpec(
    name="pavement_overlay_sn",
    description=(
        "Compute asphalt overlay thickness using the AASHTO '93 "
        "SN-deficiency method.\n"
        "\n"
        "D_overlay = (SN_required - SN_existing) / a_overlay\n"
        "\n"
        "Returns D_overlay_in (inches, rounded up to 0.5 in.).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "SN_existing": {
                "type": "number",
                "description": "Effective existing structural number (as-built × condition factor). >= 0.",
            },
            "SN_required": {
                "type": "number",
                "description": "Required structural number for remaining design period. Must be > 0.",
            },
            "a_overlay": {
                "type": "number",
                "description": "Layer coefficient of overlay material. HMA: typically 0.42–0.44/in. Must be > 0.",
            },
        },
        "required": ["SN_existing", "SN_required", "a_overlay"],
    },
)


@register(_overlay_spec, write=False)
async def run_pavement_overlay_sn(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("SN_existing", "SN_required", "a_overlay"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = overlay_thickness_sn(a["SN_existing"], a["SN_required"], a["a_overlay"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pavement_asphalt_quantity
# ---------------------------------------------------------------------------

_qty_spec = ToolSpec(
    name="pavement_asphalt_quantity",
    description=(
        "Compute asphalt mix quantity (mass) for a pavement layer.\n"
        "\n"
        "mass = length × width × thickness × density\n"
        "\n"
        "Returns volume_m3, mass_kg, and mass_tonnes.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "length_m": {
                "type": "number",
                "description": "Pavement length (m). Must be > 0.",
            },
            "width_m": {
                "type": "number",
                "description": "Pavement width (m). Must be > 0.",
            },
            "thickness_m": {
                "type": "number",
                "description": "Layer thickness (m). Must be > 0.",
            },
            "density_kg_m3": {
                "type": "number",
                "description": "Compacted HMA density (kg/m³). Default: 2350 kg/m³. Must be > 0.",
            },
        },
        "required": ["length_m", "width_m", "thickness_m"],
    },
)


@register(_qty_spec, write=False)
async def run_pavement_asphalt_quantity(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("length_m", "width_m", "thickness_m"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "density_kg_m3" in a:
        kwargs["density_kg_m3"] = a["density_kg_m3"]

    result = asphalt_quantity(a["length_m"], a["width_m"], a["thickness_m"], **kwargs)
    return ok_payload(result)
