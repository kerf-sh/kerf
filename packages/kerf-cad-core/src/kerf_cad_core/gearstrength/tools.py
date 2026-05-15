"""
kerf_cad_core.gearstrength.tools — LLM tool wrappers for AGMA gear strength.

Registers eight tools with the Kerf tool registry:

  agma_dynamic_factor    — dynamic factor Kv from quality number & pitch-line velocity
  agma_geometry_factor_J — bending geometry factor J (spur/helical)
  agma_geometry_factor_I — pitting geometry factor I
  agma_bending_stress    — AGMA 2001 bending stress σ_t
  agma_contact_stress    — AGMA 2001 contact/pitting stress σ_c
  agma_safety_factors    — SF (bending) and SH (contact) vs allowable
  agma_power_rating      — max safe power / torque for a gear pair
  agma_service_life      — stress-cycle factors YN / ZN for finite life

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
AGMA 2001-D04 — Fundamental Rating Factors and Calculation Methods for
    Involute Spur and Helical Gear Teeth
Shigley's Mechanical Engineering Design, 10th ed., §§ 14-1..14-5

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.gearstrength.rating import (
    agma_dynamic_factor,
    agma_geometry_factor_J,
    agma_geometry_factor_I,
    agma_bending_stress,
    agma_contact_stress,
    agma_safety_factors,
    agma_power_rating,
    agma_service_life,
)


# ---------------------------------------------------------------------------
# Tool: agma_dynamic_factor
# ---------------------------------------------------------------------------

_dyn_factor_spec = ToolSpec(
    name="agma_dynamic_factor",
    description=(
        "Compute the AGMA dynamic factor Kv from quality number Qv and "
        "pitch-line velocity (ft/min).\n"
        "\n"
        "Kv >= 1 amplifies the transmitted load Wt to account for dynamic "
        "tooth loads caused by gear errors and inertia.  Higher Qv (better "
        "quality) reduces Kv.\n"
        "\n"
        "Pitch-line velocity: Vt_fpm = π · d_in · n_rpm / 12.\n"
        "\n"
        "Returns Kv, validity range, and a warning if velocity exceeds the "
        "AGMA limit for the chosen quality number.\n"
        "\n"
        "Reference: AGMA 2001-D04 §6.2; Shigley 10th §14-2 Eqs (14-27)-(14-28)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Vt_fpm": {
                "type": "number",
                "description": "Pitch-line velocity (ft/min). Must be > 0.",
            },
            "Qv": {
                "type": "number",
                "description": (
                    "AGMA quality number. Range 3–12. "
                    "Typical: hobbed 5-6, shaved 7-8, ground 11-12."
                ),
            },
        },
        "required": ["Vt_fpm", "Qv"],
    },
)


@register(_dyn_factor_spec, write=False)
async def run_agma_dynamic_factor(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if a.get("Vt_fpm") is None:
        return json.dumps({"ok": False, "reason": "Vt_fpm is required"})
    if a.get("Qv") is None:
        return json.dumps({"ok": False, "reason": "Qv is required"})
    result = agma_dynamic_factor(a["Vt_fpm"], a["Qv"])
    return ok_payload(result) if result["ok"] else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: agma_geometry_factor_J
# ---------------------------------------------------------------------------

_geom_J_spec = ToolSpec(
    name="agma_geometry_factor_J",
    description=(
        "Compute the AGMA bending geometry factor J for spur (ψ=0) or "
        "helical gears.\n"
        "\n"
        "J is the Lewis form factor corrected for helical overlap.  Values "
        "are interpolated from the AGMA/Shigley Table 14-2 for 20° or 25° "
        "normal pressure angles.  A simplified helix correction is applied.\n"
        "\n"
        "Use J in: σ_t = Wt·Ko·Kv·Ks·Km·KB / (b·m·J).\n"
        "\n"
        "Reference: AGMA 908-B89; Shigley 10th §14-3 Table 14-2."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "N": {
                "type": "number",
                "description": "Number of teeth on the gear. Must be >= 12.",
            },
            "psi_deg": {
                "type": "number",
                "description": (
                    "Helix angle (degrees). 0 = spur; helical typically 15–30°."
                ),
            },
            "pressure_angle_deg": {
                "type": "number",
                "description": "Normal pressure angle (degrees). Default 20; supported 14–30.",
            },
        },
        "required": ["N", "psi_deg"],
    },
)


@register(_geom_J_spec, write=False)
async def run_agma_geometry_factor_J(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if a.get("N") is None:
        return json.dumps({"ok": False, "reason": "N is required"})
    if a.get("psi_deg") is None:
        return json.dumps({"ok": False, "reason": "psi_deg is required"})
    kwargs: dict = {}
    if "pressure_angle_deg" in a:
        kwargs["pressure_angle_deg"] = a["pressure_angle_deg"]
    result = agma_geometry_factor_J(a["N"], a["psi_deg"], **kwargs)
    return ok_payload(result) if result["ok"] else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: agma_geometry_factor_I
# ---------------------------------------------------------------------------

_geom_I_spec = ToolSpec(
    name="agma_geometry_factor_I",
    description=(
        "Compute the AGMA pitting (contact) geometry factor I for a gear pair.\n"
        "\n"
        "I accounts for the geometry of contact between the mating flanks. "
        "Used in: σ_c = Cp · √(Wt·Ko·Kv·Ks·Km / (d·b·I)).\n"
        "\n"
        "Supply the pinion as N_p (smaller gear, N_p <= N_g).\n"
        "\n"
        "Reference: Shigley 10th §14-3, Eq. (14-23)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "N_p": {
                "type": "number",
                "description": "Number of teeth on pinion (smaller gear). >= 12.",
            },
            "N_g": {
                "type": "number",
                "description": "Number of teeth on gear (larger gear). >= N_p.",
            },
            "psi_deg": {
                "type": "number",
                "description": "Helix angle (degrees). 0 = spur.",
            },
            "pressure_angle_deg": {
                "type": "number",
                "description": "Normal pressure angle (degrees). Default 20.",
            },
            "external": {
                "type": "boolean",
                "description": "True (default) = external mesh; False = internal ring gear.",
            },
        },
        "required": ["N_p", "N_g", "psi_deg"],
    },
)


@register(_geom_I_spec, write=False)
async def run_agma_geometry_factor_I(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("N_p", "N_g", "psi_deg"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    kwargs: dict = {}
    if "pressure_angle_deg" in a:
        kwargs["pressure_angle_deg"] = a["pressure_angle_deg"]
    if "external" in a:
        kwargs["external"] = a["external"]
    result = agma_geometry_factor_I(a["N_p"], a["N_g"], a["psi_deg"], **kwargs)
    return ok_payload(result) if result["ok"] else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: agma_bending_stress
# ---------------------------------------------------------------------------

_bending_spec = ToolSpec(
    name="agma_bending_stress",
    description=(
        "Compute the AGMA 2001-D04 bending stress σ_t.\n"
        "\n"
        "Metric:   σ_t = Wt·Ko·Kv·Ks·Km·KB / (b·m·J)   [MPa]\n"
        "English:  σ_t = Wt·Ko·Kv·Ks·Pd·Km·KB / (b·J)   [psi]\n"
        "\n"
        "Use metric=true for SI units (N, mm, MPa), metric=false (default) "
        "for English (lbf, in, psi).\n"
        "\n"
        "Reference: AGMA 2001-D04 §6.1; Shigley 10th Eq. (14-15)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Wt": {
                "type": "number",
                "description": "Tangential transmitted load. lbf (English) or N (metric).",
            },
            "Ko": {
                "type": "number",
                "description": "Overload factor (>= 1). Accounts for external dynamic loads.",
            },
            "Kv": {
                "type": "number",
                "description": "Dynamic factor (>= 1). From agma_dynamic_factor.",
            },
            "Ks": {
                "type": "number",
                "description": "Size factor (>= 1; typically 1.0 for Pd >= 5).",
            },
            "Km": {
                "type": "number",
                "description": "Load-distribution factor (>= 1).",
            },
            "KB": {
                "type": "number",
                "description": "Rim thickness factor (1.0 for solid blank).",
            },
            "b": {
                "type": "number",
                "description": "Face width. in (English) or mm (metric).",
            },
            "m_or_Pd": {
                "type": "number",
                "description": (
                    "Module m [mm] (metric) or diametral pitch Pd [teeth/in] (English)."
                ),
            },
            "J": {
                "type": "number",
                "description": "Bending geometry factor from agma_geometry_factor_J.",
            },
            "metric": {
                "type": "boolean",
                "description": "True = metric (N/mm/MPa); False = English (lbf/in/psi). Default false.",
            },
        },
        "required": ["Wt", "Ko", "Kv", "Ks", "Km", "KB", "b", "m_or_Pd", "J"],
    },
)


@register(_bending_spec, write=False)
async def run_agma_bending_stress(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    required = ("Wt", "Ko", "Kv", "Ks", "Km", "KB", "b", "m_or_Pd", "J")
    for field in required:
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = agma_bending_stress(
        a["Wt"], a["Ko"], a["Kv"], a["Ks"], a["Km"], a["KB"],
        a["b"], a["m_or_Pd"], a["J"],
        metric=bool(a.get("metric", False)),
    )
    return ok_payload(result) if result["ok"] else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: agma_contact_stress
# ---------------------------------------------------------------------------

_contact_spec = ToolSpec(
    name="agma_contact_stress",
    description=(
        "Compute the AGMA 2001-D04 contact (pitting) stress σ_c.\n"
        "\n"
        "σ_c = Cp · √(Wt·Ko·Kv·Ks·Km / (d_p·b·I))\n"
        "\n"
        "Cp (elastic coefficient):\n"
        "  Steel/steel English: 2300 √psi\n"
        "  Steel/steel metric:  191 √MPa\n"
        "\n"
        "Reference: AGMA 2001-D04 §6.2; Shigley 10th Eq. (14-16)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Wt": {
                "type": "number",
                "description": "Tangential transmitted load. lbf or N.",
            },
            "Ko": {"type": "number", "description": "Overload factor (>= 1)."},
            "Kv": {"type": "number", "description": "Dynamic factor (>= 1)."},
            "Ks": {"type": "number", "description": "Size factor (>= 1)."},
            "Km": {"type": "number", "description": "Load-distribution factor (>= 1)."},
            "Cp": {
                "type": "number",
                "description": (
                    "Elastic coefficient. "
                    "Steel/steel: 2300 √psi (English) or 191 √MPa (metric)."
                ),
            },
            "d_p": {
                "type": "number",
                "description": "Pinion pitch diameter. in (English) or mm (metric).",
            },
            "b": {
                "type": "number",
                "description": "Face width. in or mm.",
            },
            "I": {
                "type": "number",
                "description": "Pitting geometry factor from agma_geometry_factor_I.",
            },
            "metric": {
                "type": "boolean",
                "description": "True = metric (N/mm/MPa). Default false.",
            },
        },
        "required": ["Wt", "Ko", "Kv", "Ks", "Km", "Cp", "d_p", "b", "I"],
    },
)


@register(_contact_spec, write=False)
async def run_agma_contact_stress(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    required = ("Wt", "Ko", "Kv", "Ks", "Km", "Cp", "d_p", "b", "I")
    for field in required:
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = agma_contact_stress(
        a["Wt"], a["Ko"], a["Kv"], a["Ks"], a["Km"], a["Cp"],
        a["d_p"], a["b"], a["I"],
        metric=bool(a.get("metric", False)),
    )
    return ok_payload(result) if result["ok"] else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: agma_safety_factors
# ---------------------------------------------------------------------------

_safety_spec = ToolSpec(
    name="agma_safety_factors",
    description=(
        "Compute AGMA 2001-D04 safety factors SF (bending) and SH (contact).\n"
        "\n"
        "Allowable bending stress: sigma_t_all = S_t · YN / (K_T · K_R)\n"
        "Allowable contact stress: sigma_c_all = S_c · ZN / (K_T · K_R)\n"
        "SF = sigma_t_all / sigma_b  (>= 1 required; >= 1.2 recommended)\n"
        "SH = sigma_c_all / sigma_c  (>= 1 required; >= 1.2 recommended)\n"
        "\n"
        "Reference: AGMA 2001-D04 §4.1; Shigley 10th §14-5."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "sigma_b": {
                "type": "number",
                "description": "Actual AGMA bending stress σ_t (psi or MPa).",
            },
            "sigma_c": {
                "type": "number",
                "description": "Actual AGMA contact stress σ_c (psi or MPa).",
            },
            "S_t": {
                "type": "number",
                "description": (
                    "Allowable bending stress number (material, psi or MPa). "
                    "Typical carburised steel: 65 kpsi / 450 MPa."
                ),
            },
            "S_c": {
                "type": "number",
                "description": (
                    "Allowable contact stress number (material, psi or MPa). "
                    "Typical carburised steel: 225 kpsi / 1550 MPa."
                ),
            },
            "YN": {
                "type": "number",
                "description": "Bending stress-cycle factor (default 1.0).",
            },
            "ZN": {
                "type": "number",
                "description": "Contact stress-cycle factor (default 1.0).",
            },
            "K_T": {
                "type": "number",
                "description": "Temperature factor (default 1.0 for T < 120°C).",
            },
            "K_R": {
                "type": "number",
                "description": "Reliability factor (1.0 → 90%, 1.25 → 99%). Default 1.0.",
            },
        },
        "required": ["sigma_b", "sigma_c", "S_t", "S_c"],
    },
)


@register(_safety_spec, write=False)
async def run_agma_safety_factors(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("sigma_b", "sigma_c", "S_t", "S_c"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    kwargs: dict = {}
    for opt in ("YN", "ZN", "K_T", "K_R"):
        if opt in a:
            kwargs[opt] = a[opt]
    result = agma_safety_factors(
        a["sigma_b"], a["sigma_c"], a["S_t"], a["S_c"], **kwargs
    )
    return ok_payload(result) if result["ok"] else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: agma_power_rating
# ---------------------------------------------------------------------------

_power_spec = ToolSpec(
    name="agma_power_rating",
    description=(
        "Compute the maximum safe transmitted power and torque for a gear pair "
        "based on AGMA 2001-D04 allowable stresses.\n"
        "\n"
        "Solves for the governing tangential load Wt from both bending and "
        "contact allowable stress limits, then converts to power (hp or kW) "
        "and torque.\n"
        "\n"
        "Use metric=true for SI (N, mm, kW, MPa), default is English (lbf, in, hp, psi).\n"
        "\n"
        "Reference: AGMA 2001-D04; Shigley 10th §14-5."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "S_t": {"type": "number", "description": "Allowable bending stress number (psi or MPa)."},
            "S_c": {"type": "number", "description": "Allowable contact stress number (psi or MPa)."},
            "Cp": {
                "type": "number",
                "description": "Elastic coefficient. Steel/steel: 2300 √psi or 191 √MPa.",
            },
            "b": {"type": "number", "description": "Face width. in or mm."},
            "m_or_Pd": {"type": "number", "description": "Module m [mm] or diametral pitch Pd [1/in]."},
            "d_p": {"type": "number", "description": "Pinion pitch diameter. in or mm."},
            "N_p": {"type": "number", "description": "Pinion tooth count."},
            "N_g": {"type": "number", "description": "Gear tooth count (>= N_p)."},
            "psi_deg": {"type": "number", "description": "Helix angle (deg). 0 = spur."},
            "n_rpm": {"type": "number", "description": "Pinion rotational speed (rpm)."},
            "metric": {"type": "boolean", "description": "True = SI units. Default false."},
            "Ko": {"type": "number", "description": "Overload factor. Default 1.0."},
            "Ks": {"type": "number", "description": "Size factor. Default 1.0."},
            "Km": {"type": "number", "description": "Load-distribution factor. Default 1.3."},
            "KB": {"type": "number", "description": "Rim thickness factor. Default 1.0."},
            "Qv": {"type": "number", "description": "AGMA quality number (3–12). Default 6."},
            "K_T": {"type": "number", "description": "Temperature factor. Default 1.0."},
            "K_R": {"type": "number", "description": "Reliability factor. Default 1.0."},
            "pressure_angle_deg": {"type": "number", "description": "Normal pressure angle. Default 20."},
            "YN": {"type": "number", "description": "Bending cycle factor. Default 1.0."},
            "ZN": {"type": "number", "description": "Contact cycle factor. Default 1.0."},
        },
        "required": ["S_t", "S_c", "Cp", "b", "m_or_Pd", "d_p", "N_p", "N_g", "psi_deg", "n_rpm"],
    },
)


@register(_power_spec, write=False)
async def run_agma_power_rating(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    required = ("S_t", "S_c", "Cp", "b", "m_or_Pd", "d_p", "N_p", "N_g", "psi_deg", "n_rpm")
    for field in required:
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    kwargs: dict = {}
    for opt in ("metric", "Ko", "Ks", "Km", "KB", "Qv", "K_T", "K_R",
                "pressure_angle_deg", "YN", "ZN"):
        if opt in a:
            kwargs[opt] = a[opt]
    result = agma_power_rating(
        a["S_t"], a["S_c"], a["Cp"], a["b"], a["m_or_Pd"],
        a["d_p"], a["N_p"], a["N_g"], a["psi_deg"], a["n_rpm"],
        **kwargs,
    )
    return ok_payload(result) if result["ok"] else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: agma_service_life
# ---------------------------------------------------------------------------

_life_spec = ToolSpec(
    name="agma_service_life",
    description=(
        "Compute AGMA 2001-D04 stress-cycle factors YN (bending) and ZN (contact) "
        "for a given number of stress cycles.\n"
        "\n"
        "YN and ZN scale the allowable stresses for finite service life:\n"
        "  sigma_t_all = S_t · YN / (K_T · K_R)\n"
        "  sigma_c_all = S_c · ZN / (K_T · K_R)\n"
        "\n"
        "At very long life both approach ~0.9 (conservative AGMA plateau).\n"
        "\n"
        "Cycles for a rotating gear: N = n_rpm × 60 × hours.\n"
        "\n"
        "Reference: AGMA 2001-D04 §§ 4.2.1-4.2.2; Shigley 10th Eqs. (14-31)-(14-35)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "N_cycles": {
                "type": "number",
                "description": "Number of stress cycles. Must be > 0.",
            },
            "hardness_HB": {
                "type": "number",
                "description": (
                    "Brinell hardness HB (default 200). "
                    "Through-hardened valid range: 180–400 HB."
                ),
            },
            "gear_type": {
                "type": "string",
                "enum": ["through_hardened"],
                "description": "Gear heat-treatment type. Currently: through_hardened.",
            },
        },
        "required": ["N_cycles"],
    },
)


@register(_life_spec, write=False)
async def run_agma_service_life(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if a.get("N_cycles") is None:
        return json.dumps({"ok": False, "reason": "N_cycles is required"})
    kwargs: dict = {}
    if "hardness_HB" in a:
        kwargs["hardness_HB"] = a["hardness_HB"]
    if "gear_type" in a:
        kwargs["gear_type"] = a["gear_type"]
    result = agma_service_life(a["N_cycles"], **kwargs)
    return ok_payload(result) if result["ok"] else json.dumps(result)
