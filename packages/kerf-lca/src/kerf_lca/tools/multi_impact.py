"""
LLM tool: multi_impact

Multi-impact characterisation beyond GWP100: acidification, eutrophication,
human toxicity, water consumption, particulate matter.

Input schema (JSON)
-------------------
product_breakdown — (array, required) list of:
    { material_id: str, mass_kg: float }
    material_id must match an ICE v3 key (see list_materials tool).

Output
------
JSON: {
    impacts: { gwp100, ap, ep, htp, water, pm25 },
    units:   { ... },
    methods: { ... },
    warnings: [...],
}
"""

from __future__ import annotations

import json

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
    from kerf_core.utils.context import ProjectCtx
except ImportError:
    from kerf_lca._compat import ToolSpec, err_payload, ok_payload, register, ProjectCtx

from kerf_lca.impact_categories import multi_impact as _multi_impact

multi_impact_spec = ToolSpec(
    name="multi_impact",
    description=(
        "Compute multi-impact characterisation beyond GWP100 for a product "
        "material breakdown. Categories: acidification (kg SO₂-eq, CML 2002), "
        "eutrophication (kg PO₄-eq, CML 2002), human toxicity (CTUh, USEtox), "
        "water consumption (m³), particulate matter (kg PM2.5-eq, ReCiPe 2016)."
    ),
    input_schema={
        "type": "object",
        "required": ["product_breakdown"],
        "properties": {
            "product_breakdown": {
                "type": "array",
                "description": "List of {material_id, mass_kg} items.",
                "items": {
                    "type": "object",
                    "required": ["material_id", "mass_kg"],
                    "properties": {
                        "material_id": {"type": "string"},
                        "mass_kg": {"type": "number"},
                    },
                },
            },
        },
    },
)


@register(multi_impact_spec)
async def run_multi_impact(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args) if args else {}
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    breakdown = a.get("product_breakdown")
    if not isinstance(breakdown, list):
        return err_payload("'product_breakdown' must be an array", "BAD_ARGS")

    try:
        result = _multi_impact(breakdown)
    except Exception as e:
        return err_payload(str(e), "CALC_ERROR")

    return ok_payload(result)
