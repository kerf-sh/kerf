"""
kerf_cad_core.welding.tools — LLM tool wrappers for weld process engineering.

Registers twelve tools with the Kerf tool registry:

  weld_arc_heat_input          — arc heat input HI = η·V·I/(1000·v)
  weld_carbon_equivalent_iiw   — IIW carbon equivalent CE
  weld_preheat_temperature     — minimum preheat temperature (AWS D1.1 / Yurioka)
  weld_cooling_time_t85        — t8/5 cooling time (Rykalin)
  weld_fillet_volume           — fillet weld metal volume
  weld_groove_volume           — groove (V) weld metal volume
  weld_deposition_time         — deposition time from volume and deposition rate
  weld_electrode_consumption   — gross electrode / wire mass including spatter
  weld_number_of_passes        — estimated number of passes to fill groove
  weld_angular_distortion      — transverse angular distortion (Okerblom)
  weld_longitudinal_distortion — longitudinal bowing distortion
  weld_interpass_check         — interpass temperature compliance check

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
AWS D1.1/D1.1M:2020 — Structural Welding Code (Steel)
IIW Doc. IXJ-123-85 — CE (IIW) formula
Lincoln Electric "The Procedure Handbook of Arc Welding", 14th ed.
Radaj D. (1992) — Heat Effects of Welding, Springer

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.welding.process import (
    arc_heat_input,
    carbon_equivalent_iiw,
    preheat_temperature,
    cooling_time_t85,
    fillet_weld_volume,
    groove_weld_volume,
    deposition_time,
    electrode_consumption,
    number_of_passes,
    angular_distortion,
    longitudinal_distortion,
    interpass_temperature_check,
)


# ---------------------------------------------------------------------------
# Tool: weld_arc_heat_input
# ---------------------------------------------------------------------------

_arc_heat_input_spec = ToolSpec(
    name="weld_arc_heat_input",
    description=(
        "Compute the arc heat input per unit weld length.\n"
        "\n"
        "HI = η × V × I / (1000 × v)   [kJ/mm]\n"
        "\n"
        "where η is the thermal efficiency of the welding process, V is the arc "
        "voltage, I is the welding current, and v is the travel speed.\n"
        "\n"
        "Typical process efficiencies: SMAW≈0.80, GMAW/FCAW≈0.85, SAW≈0.99, GTAW≈0.60.\n"
        "\n"
        "Flags excessive HI (> 3.5 kJ/mm) in warnings.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "eta": {
                "type": "number",
                "description": (
                    "Thermal efficiency of the welding process (0 < η ≤ 1). "
                    "SMAW≈0.80, GMAW≈0.85, SAW≈0.99, GTAW≈0.60."
                ),
            },
            "V": {
                "type": "number",
                "description": "Arc voltage (V). Must be > 0.",
            },
            "I": {
                "type": "number",
                "description": "Welding current (A). Must be > 0.",
            },
            "v": {
                "type": "number",
                "description": "Travel speed (mm/s). Must be > 0.",
            },
        },
        "required": ["eta", "V", "I", "v"],
    },
)


@register(_arc_heat_input_spec, write=False)
async def run_arc_heat_input(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("eta", "V", "I", "v"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = arc_heat_input(a["eta"], a["V"], a["I"], a["v"])
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: weld_carbon_equivalent_iiw
# ---------------------------------------------------------------------------

_ce_iiw_spec = ToolSpec(
    name="weld_carbon_equivalent_iiw",
    description=(
        "Compute the IIW carbon equivalent for weld preheat assessment.\n"
        "\n"
        "CE = C + Mn/6 + (Cr + Mo + V)/5 + (Cu + Ni)/15\n"
        "\n"
        "All composition values in weight percent (wt%).\n"
        "CE > 0.45 → preheat generally required (AWS D1.1).\n"
        "CE > 0.70 → high hydrogen-cracking risk.\n"
        "\n"
        "Flags elevated CE in warnings.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "C":  {"type": "number", "description": "Carbon content (wt%). Must be >= 0."},
            "Mn": {"type": "number", "description": "Manganese content (wt%). Must be >= 0."},
            "Si": {"type": "number", "description": "Silicon content (wt%). Default 0."},
            "Cr": {"type": "number", "description": "Chromium content (wt%). Default 0."},
            "Mo": {"type": "number", "description": "Molybdenum content (wt%). Default 0."},
            "V":  {"type": "number", "description": "Vanadium content (wt%). Default 0."},
            "Cu": {"type": "number", "description": "Copper content (wt%). Default 0."},
            "Ni": {"type": "number", "description": "Nickel content (wt%). Default 0."},
        },
        "required": ["C", "Mn"],
    },
)


@register(_ce_iiw_spec, write=False)
async def run_carbon_equivalent_iiw(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("C") is None:
        return json.dumps({"ok": False, "reason": "C is required"})
    if a.get("Mn") is None:
        return json.dumps({"ok": False, "reason": "Mn is required"})

    kwargs: dict = {}
    for opt in ("Si", "Cr", "Mo", "V", "Cu", "Ni"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = carbon_equivalent_iiw(a["C"], a["Mn"], **kwargs)
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: weld_preheat_temperature
# ---------------------------------------------------------------------------

_preheat_spec = ToolSpec(
    name="weld_preheat_temperature",
    description=(
        "Compute the minimum preheat temperature for a weld per AWS D1.1 / "
        "Yurioka approach.\n"
        "\n"
        "Uses two methods and returns the more conservative:\n"
        "  Method A (AWS D1.1 empirical): T_p = 350√(CE) − 25  (°C)\n"
        "  Method B (Yurioka Pcm):        T_p = 1440·Pcm − 392 (°C)\n"
        "\n"
        "A thickness correction (+10°C per mm above 25 mm) and heat-input "
        "reduction (−5°C per kJ/mm above 1.0 kJ/mm) are applied.\n"
        "Result is clamped to 0°C (no preheat required if formula gives negative).\n"
        "\n"
        "Flags cracking risk in warnings.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "CE": {
                "type": "number",
                "description": "IIW carbon equivalent (dimensionless). Must be >= 0.",
            },
            "t_mm": {
                "type": "number",
                "description": "Base metal / plate thickness (mm). Must be > 0.",
            },
            "HI_kJ_mm": {
                "type": "number",
                "description": "Arc heat input (kJ/mm). Must be > 0.",
            },
        },
        "required": ["CE", "t_mm", "HI_kJ_mm"],
    },
)


@register(_preheat_spec, write=False)
async def run_preheat_temperature(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("CE", "t_mm", "HI_kJ_mm"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = preheat_temperature(a["CE"], a["t_mm"], a["HI_kJ_mm"])
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: weld_cooling_time_t85
# ---------------------------------------------------------------------------

_t85_spec = ToolSpec(
    name="weld_cooling_time_t85",
    description=(
        "Estimate the weld cooling time t8/5 (time from 800 °C to 500 °C) in "
        "seconds using the Rykalin simplified formula.\n"
        "\n"
        "Butt weld (3D heat flow, thick plate):\n"
        "  t8/5 = (6700−5T₀)×Q²×(1/500−1/800)² / (2π×λ)\n"
        "\n"
        "Fillet weld (2D heat flow, thin plate):\n"
        "  t8/5 = (4300−4.3T₀)×Q²×(1/500²−1/800²) / (2π²×λ²×ρc×h²)\n"
        "\n"
        "Q = HI_kJ_mm × 1000 (J/mm), λ = 0.40 J/(mm·s·°C), ρc = 3.6e-3 J/(mm³·°C).\n"
        "\n"
        "Flags short t8/5 (martensite risk) and long t8/5 (grain growth) in warnings.  "
        "Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "HI_kJ_mm": {
                "type": "number",
                "description": "Arc heat input (kJ/mm). Must be > 0.",
            },
            "T_preheat_C": {
                "type": "number",
                "description": "Preheat / interpass temperature (°C). Must be >= 0.",
            },
            "t_mm": {
                "type": "number",
                "description": "Plate thickness (mm). Must be > 0.",
            },
            "joint_type": {
                "type": "string",
                "enum": ["butt", "fillet"],
                "description": (
                    "'butt' (3D heat flow, default) or 'fillet' (2D heat flow)."
                ),
            },
        },
        "required": ["HI_kJ_mm", "T_preheat_C", "t_mm"],
    },
)


@register(_t85_spec, write=False)
async def run_cooling_time_t85(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("HI_kJ_mm", "T_preheat_C", "t_mm"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "joint_type" in a:
        kwargs["joint_type"] = a["joint_type"]

    result = cooling_time_t85(a["HI_kJ_mm"], a["T_preheat_C"], a["t_mm"], **kwargs)
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: weld_fillet_volume
# ---------------------------------------------------------------------------

_fillet_vol_spec = ToolSpec(
    name="weld_fillet_volume",
    description=(
        "Compute the weld metal volume for an equal-leg fillet weld.\n"
        "\n"
        "Cross-section = right-isosceles triangle with leg = leg_mm.\n"
        "Area = leg² / 2,  Volume = Area × length,  Throat = leg / √2.\n"
        "\n"
        "Flags undersized (<3 mm) or oversized (>20 mm) legs in warnings.  "
        "Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "leg_mm":    {"type": "number", "description": "Fillet leg length (mm). Must be > 0."},
            "length_mm": {"type": "number", "description": "Weld run length (mm). Must be > 0."},
        },
        "required": ["leg_mm", "length_mm"],
    },
)


@register(_fillet_vol_spec, write=False)
async def run_fillet_weld_volume(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("leg_mm", "length_mm"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = fillet_weld_volume(a["leg_mm"], a["length_mm"])
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: weld_groove_volume
# ---------------------------------------------------------------------------

_groove_vol_spec = ToolSpec(
    name="weld_groove_volume",
    description=(
        "Compute the weld metal volume for a V-groove weld (trapezoidal "
        "cross-section).\n"
        "\n"
        "area   = (w_top + w_root) / 2 × (depth − root_face)\n"
        "volume = area × length\n"
        "\n"
        "If width_top_mm = 0, it is computed from included_angle_deg and depth.\n"
        "If width_root_mm = 0, root_gap_mm is used.\n"
        "\n"
        "Flags narrow (<30°) or wide (>90°) groove angles in warnings.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "depth_mm":      {"type": "number", "description": "Total groove depth (mm). Must be > 0."},
            "width_top_mm":  {"type": "number", "description": "Top groove width (mm). 0 = compute from angle."},
            "width_root_mm": {"type": "number", "description": "Root width (mm). 0 = use root_gap_mm."},
            "length_mm":     {"type": "number", "description": "Weld run length (mm). Must be > 0."},
            "included_angle_deg": {
                "type": "number",
                "description": "Groove included angle (degrees). Default 60°.",
            },
            "root_face_mm": {
                "type": "number",
                "description": "Root face / land height (mm). Default 2 mm.",
            },
            "root_gap_mm": {
                "type": "number",
                "description": "Root opening (mm). Default 3 mm.",
            },
        },
        "required": ["depth_mm", "width_top_mm", "width_root_mm", "length_mm"],
    },
)


@register(_groove_vol_spec, write=False)
async def run_groove_weld_volume(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("depth_mm", "width_top_mm", "width_root_mm", "length_mm"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("included_angle_deg", "root_face_mm", "root_gap_mm"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = groove_weld_volume(
        a["depth_mm"], a["width_top_mm"], a["width_root_mm"], a["length_mm"], **kwargs
    )
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: weld_deposition_time
# ---------------------------------------------------------------------------

_dep_time_spec = ToolSpec(
    name="weld_deposition_time",
    description=(
        "Compute weld deposition time from weld metal volume and deposition rate.\n"
        "\n"
        "mass_kg = volume_mm3 × density_kg_mm3\n"
        "time_s  = mass_kg / deposition_rate_kg_h × 3600\n"
        "\n"
        "Typical deposition rates: SMAW 1–5 kg/h, GMAW 3–8 kg/h, SAW 5–20 kg/h.\n"
        "\n"
        "Flags excessively long jobs (>8 hours) in warnings.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "volume_mm3": {
                "type": "number",
                "description": "Weld metal volume (mm³). Must be > 0.",
            },
            "deposition_rate_kg_h": {
                "type": "number",
                "description": "Deposition rate (kg/h). Must be > 0.",
            },
            "density_kg_mm3": {
                "type": "number",
                "description": (
                    "Weld metal density (kg/mm³). Default 7.85e-6 (structural steel)."
                ),
            },
        },
        "required": ["volume_mm3", "deposition_rate_kg_h"],
    },
)


@register(_dep_time_spec, write=False)
async def run_deposition_time(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("volume_mm3", "deposition_rate_kg_h"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "density_kg_mm3" in a:
        kwargs["density_kg_mm3"] = a["density_kg_mm3"]

    result = deposition_time(a["volume_mm3"], a["deposition_rate_kg_h"], **kwargs)
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: weld_electrode_consumption
# ---------------------------------------------------------------------------

_elec_spec = ToolSpec(
    name="weld_electrode_consumption",
    description=(
        "Compute gross electrode/wire mass consumed including spatter & stub losses.\n"
        "\n"
        "deposit_mass_kg = volume_mm3 × density_kg_mm3\n"
        "electrode_mass_kg = deposit_mass_kg / deposition_efficiency\n"
        "\n"
        "Typical deposition efficiencies:\n"
        "  SMAW ≈ 0.60–0.75,  GMAW ≈ 0.93–0.98,  FCAW ≈ 0.82–0.90,  SAW ≈ 0.99.\n"
        "\n"
        "Flags low efficiency (<60%) in warnings.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "volume_mm3": {
                "type": "number",
                "description": "Weld metal volume (mm³). Must be > 0.",
            },
            "density_kg_mm3": {
                "type": "number",
                "description": "Weld metal density (kg/mm³). Default 7.85e-6 (steel).",
            },
            "deposition_efficiency": {
                "type": "number",
                "description": (
                    "Fraction of electrode/wire deposited as weld metal (0–1]. "
                    "Default 0.65 (SMAW conservative)."
                ),
            },
        },
        "required": ["volume_mm3"],
    },
)


@register(_elec_spec, write=False)
async def run_electrode_consumption(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("volume_mm3") is None:
        return json.dumps({"ok": False, "reason": "volume_mm3 is required"})

    kwargs: dict = {}
    for opt in ("density_kg_mm3", "deposition_efficiency"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = electrode_consumption(a["volume_mm3"], **kwargs)
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: weld_number_of_passes
# ---------------------------------------------------------------------------

_passes_spec = ToolSpec(
    name="weld_number_of_passes",
    description=(
        "Estimate the number of weld passes to fill a groove.\n"
        "\n"
        "n_passes = ceil(groove_area_mm2 / pass_area_mm2)\n"
        "\n"
        "Typical pass areas: SMAW 3.2 mm electrode ≈ 30–50 mm², "
        "GMAW 1.2 mm wire ≈ 20–40 mm².\n"
        "\n"
        "Flags high pass counts (>30) in warnings.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "groove_area_mm2": {
                "type": "number",
                "description": "Total groove cross-section area (mm²). Must be > 0.",
            },
            "pass_area_mm2": {
                "type": "number",
                "description": "Average weld pass cross-section area (mm²). Must be > 0.",
            },
        },
        "required": ["groove_area_mm2", "pass_area_mm2"],
    },
)


@register(_passes_spec, write=False)
async def run_number_of_passes(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("groove_area_mm2", "pass_area_mm2"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = number_of_passes(a["groove_area_mm2"], a["pass_area_mm2"])
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: weld_angular_distortion
# ---------------------------------------------------------------------------

_ang_dist_spec = ToolSpec(
    name="weld_angular_distortion",
    description=(
        "Estimate transverse (angular) distortion for a fillet weld.\n"
        "\n"
        "θ (rad) = 0.015 × HI_kJ_mm × leg_mm / t_mm²  (Okerblom empirical)\n"
        "\n"
        "Flags >3° (practical concern) and >10° (severe) in warnings.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "HI_kJ_mm": {
                "type": "number",
                "description": "Arc heat input (kJ/mm). Must be > 0.",
            },
            "t_mm": {
                "type": "number",
                "description": "Plate thickness (mm). Must be > 0.",
            },
            "leg_mm": {
                "type": "number",
                "description": "Fillet weld leg length (mm). Must be > 0.",
            },
        },
        "required": ["HI_kJ_mm", "t_mm", "leg_mm"],
    },
)


@register(_ang_dist_spec, write=False)
async def run_angular_distortion(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("HI_kJ_mm", "t_mm", "leg_mm"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = angular_distortion(a["HI_kJ_mm"], a["t_mm"], a["leg_mm"])
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: weld_longitudinal_distortion
# ---------------------------------------------------------------------------

_long_dist_spec = ToolSpec(
    name="weld_longitudinal_distortion",
    description=(
        "Estimate longitudinal (bowing) distortion of a welded member.\n"
        "\n"
        "Uses the simplified Lincoln Electric / thermal-stress model:\n"
        "δ (mm) = 3.33 × HI_kJ_mm × L² / (A × E)\n"
        "\n"
        "Flags δ > L/1000 (typical fabrication tolerance) in warnings.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "HI_kJ_mm": {
                "type": "number",
                "description": "Arc heat input (kJ/mm). Must be > 0.",
            },
            "length_mm": {
                "type": "number",
                "description": "Weld length / member length (mm). Must be > 0.",
            },
            "A_mm2": {
                "type": "number",
                "description": "Cross-sectional area of the member (mm²). Must be > 0.",
            },
            "E_MPa": {
                "type": "number",
                "description": (
                    "Young's modulus (MPa). Default 210 000 MPa (structural steel)."
                ),
            },
        },
        "required": ["HI_kJ_mm", "length_mm", "A_mm2"],
    },
)


@register(_long_dist_spec, write=False)
async def run_longitudinal_distortion(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("HI_kJ_mm", "length_mm", "A_mm2"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "E_MPa" in a:
        kwargs["E_MPa"] = a["E_MPa"]

    result = longitudinal_distortion(a["HI_kJ_mm"], a["length_mm"], a["A_mm2"], **kwargs)
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: weld_interpass_check
# ---------------------------------------------------------------------------

_interpass_spec = ToolSpec(
    name="weld_interpass_check",
    description=(
        "Check that the interpass temperature satisfies AWS D1.1 limits.\n"
        "\n"
        "Requirements:\n"
        "  T_interpass >= T_preheat   (must maintain minimum preheat)\n"
        "  T_interpass <= T_max       (must not exceed maximum; default 250 °C)\n"
        "\n"
        "Returns compliance status and margin below maximum.  "
        "Flags violations in warnings.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "T_preheat_C": {
                "type": "number",
                "description": "Minimum preheat temperature (°C). Must be >= 0.",
            },
            "T_interpass_C": {
                "type": "number",
                "description": "Measured interpass temperature (°C). Must be >= 0.",
            },
            "T_max_C": {
                "type": "number",
                "description": (
                    "Maximum allowable interpass temperature (°C). "
                    "Default 250 °C (AWS D1.1 §3.7 for structural carbon steel)."
                ),
            },
        },
        "required": ["T_preheat_C", "T_interpass_C"],
    },
)


@register(_interpass_spec, write=False)
async def run_interpass_temperature_check(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("T_preheat_C", "T_interpass_C"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "T_max_C" in a:
        kwargs["T_max_C"] = a["T_max_C"]

    result = interpass_temperature_check(
        a["T_preheat_C"], a["T_interpass_C"], **kwargs
    )
    return ok_payload(result) if result.get("ok") else json.dumps(result)
