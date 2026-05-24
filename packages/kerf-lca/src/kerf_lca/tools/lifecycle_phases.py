"""
LLM tool: lifecycle_phases

Full ISO 14040/44 multi-phase LCA: use-phase energy, transport, end-of-life,
and full lifecycle summary.

Input schema (JSON)
-------------------
product           — (string) product or part name
cradle_to_gate_gwp — (number, optional) Phase 1 GWP in kg CO₂-eq from lca_report
functional_unit   — (string, optional) FU declaration, e.g. "1 kg of part"
use_phase         — (object, optional):
    lifetime_years      (number)
    annual_energy_kWh   (number)
    region              (string) US | EU | CN | ZA | ... (default WORLD)
    grid_emission_factor_kgCO2_per_kWh  (number, optional override)
transport         — (object, optional):
    mass_kg       (number)
    distance_km   (number)
    mode          (string) truck | rail | sea | air
eol               — (object, optional):
    mass_kg              (number)
    scenario             (string) landfill | incinerate | recycle
    material_gwp_factor  (number, optional) cradle-to-gate factor for recycle credit
    recycle_allocation   (number, optional) 0–1, default 0.5

Output
------
JSON: { product, functional_unit, total_gwp_kg_co2_eq, phases: [...], warnings: [...] }
"""

from __future__ import annotations

import json

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
    from kerf_core.utils.context import ProjectCtx
except ImportError:
    from kerf_lca._compat import ToolSpec, err_payload, ok_payload, register, ProjectCtx

from kerf_lca.phases import lifecycle_summary

lifecycle_phases_spec = ToolSpec(
    name="lifecycle_phases",
    description=(
        "Compute a full ISO 14040/44 lifecycle GWP assessment across all phases: "
        "Phase 1 cradle-to-gate (supply an existing lca_report result), "
        "Phase 2 use-phase operational energy, "
        "Phase 3 transport, and "
        "Phase 4 end-of-life (landfill / incinerate / recycle with allocation). "
        "Returns total lifecycle GWP (kg CO₂-eq) and per-phase breakdown."
    ),
    input_schema={
        "type": "object",
        "required": ["product"],
        "properties": {
            "product": {"type": "string", "description": "Product or assembly name."},
            "cradle_to_gate_gwp": {
                "type": "number",
                "description": "Phase 1 embodied GWP from lca_report (kg CO₂-eq).",
            },
            "functional_unit": {
                "type": "string",
                "description": "Functional unit declaration, e.g. '1 kg bracket'.",
            },
            "use_phase": {
                "type": "object",
                "description": "Use-phase energy arguments.",
                "properties": {
                    "lifetime_years": {"type": "number"},
                    "annual_energy_kWh": {"type": "number"},
                    "region": {"type": "string"},
                    "grid_emission_factor_kgCO2_per_kWh": {"type": "number"},
                },
                "required": ["lifetime_years", "annual_energy_kWh"],
            },
            "transport": {
                "type": "object",
                "description": "Transport-phase arguments.",
                "properties": {
                    "mass_kg": {"type": "number"},
                    "distance_km": {"type": "number"},
                    "mode": {"type": "string", "enum": ["truck", "rail", "sea", "air"]},
                },
                "required": ["mass_kg", "distance_km"],
            },
            "eol": {
                "type": "object",
                "description": "End-of-life arguments.",
                "properties": {
                    "mass_kg": {"type": "number"},
                    "scenario": {"type": "string", "enum": ["landfill", "incinerate", "recycle"]},
                    "material_gwp_factor": {"type": "number"},
                    "recycle_allocation": {"type": "number"},
                },
                "required": ["mass_kg", "scenario"],
            },
        },
    },
)


@register(lifecycle_phases_spec)
async def run_lifecycle_phases(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args) if args else {}
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    product = a.get("product")
    if not product:
        return err_payload("'product' is required", "BAD_ARGS")

    cradle_gwp = float(a.get("cradle_to_gate_gwp") or 0.0)
    fu = a.get("functional_unit", "1 unit")

    use_args = a.get("use_phase")
    transport_args = a.get("transport")
    eol_args = a.get("eol")

    try:
        summary = lifecycle_summary(
            product,
            cradle_to_gate_gwp=cradle_gwp,
            use_args=use_args,
            transport_args=transport_args,
            eol_args=eol_args,
            functional_unit=fu,
        )
    except Exception as e:
        return err_payload(str(e), "CALC_ERROR")

    return ok_payload(summary.to_dict())
