"""
jewelry_metal_cost LLM tool
============================

Registers the `jewelry_metal_cost` tool with the Kerf tool registry.
The tool computes metal weight, casting weight, and itemised casting cost
from a volume (in mm³) and optional per-metal price inputs.

No project context is required — all calculations are pure math.
The ProjectCtx is accepted to conform to the registry call signature but
is not used.
"""

from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401 — required by @register

from kerf_cad_core.jewelry.metal_cost import (
    METAL_DENSITY_G_CM3,
    METAL_LABELS,
    casting_cost,
    multi_metal_compare,
)

# ---------------------------------------------------------------------------
# Tool spec
# ---------------------------------------------------------------------------

jewelry_metal_cost_spec = ToolSpec(
    name="jewelry_metal_cost",
    description=(
        "Estimate metal weight and casting cost for a jewelry piece.\n"
        "\n"
        "Given a part volume (in mm³) and metal selection, returns:\n"
        "  - net weight (g / dwt / ozt)\n"
        "  - casting gross weight with sprue/button/flashing allowance\n"
        "  - itemised cost breakdown (metal material + labor + finishing)\n"
        "  - optional multi-metal comparison table\n"
        "\n"
        "Volume can be entered manually or read from a OCCT volume query "
        "(GProp_GProps.Mass() in mm model units). Metal price is a user "
        "input — no live feed. Use spot gold/silver prices as a baseline "
        "and add your supplier's premium.\n"
        "\n"
        "Valid metal keys (pass as `metal`):\n"
        "  Gold:     10k_yellow, 14k_yellow, 18k_yellow, 22k_yellow, 24k_yellow\n"
        "            10k_white,  14k_white,  18k_white\n"
        "            10k_rose,   14k_rose,   18k_rose\n"
        "  Platinum: platinum_950\n"
        "  Palladium: palladium_950\n"
        "  Silver:   sterling_925, fine_silver\n"
        "  Other:    titanium, brass, bronze"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "volume_mm3": {
                "type": "number",
                "description": (
                    "Part volume in cubic millimetres. In OCCT/Kerf this is the "
                    "value returned by GProp_GProps.Mass() when model units are mm."
                ),
            },
            "metal": {
                "type": "string",
                "description": (
                    "Metal key.  See tool description for the full list. "
                    "Mutually exclusive with density_g_cm3."
                ),
            },
            "density_g_cm3": {
                "type": "number",
                "description": (
                    "Explicit density override in g/cm³. Use when you have "
                    "already resolved the density from a .material file "
                    "(physical.rho_kg_m3 / 1000). Mutually exclusive with metal."
                ),
            },
            "metal_price_per_gram": {
                "type": "number",
                "description": (
                    "Metal price in your currency per gram. "
                    "Example: 18k yellow gold ≈ $38 USD/g at ~$1950/ozt spot "
                    "(varies daily; check your supplier). Default 0."
                ),
            },
            "labor": {
                "type": "number",
                "description": "Bench labor cost (casting + cleanup + polish). Default 0.",
            },
            "finishing": {
                "type": "number",
                "description": "Finishing / plating / rhodium cost. Default 0.",
            },
            "casting_allowance_pct": {
                "type": "number",
                "description": (
                    "Sprue / button / flashing overhead as a percentage of net weight. "
                    "Default 15. Typical range 10 (optimised gate) – 25 (complex mould)."
                ),
            },
            "compare_metals": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional list of metal keys to include in a multi-metal "
                    "comparison table in addition to the primary estimate. "
                    "If omitted no comparison table is returned."
                ),
            },
            "compare_prices": {
                "type": "object",
                "description": (
                    "Optional per-metal price overrides for the comparison table "
                    "{metal_key: price_per_gram}. Metals absent from this map "
                    "use price 0 (weight-only rows)."
                ),
                "additionalProperties": {"type": "number"},
            },
        },
        "required": ["volume_mm3"],
    },
)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

@register(jewelry_metal_cost_spec, write=False)
async def run_jewelry_metal_cost(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    # -- volume ---------------------------------------------------------------
    volume_mm3 = a.get("volume_mm3")
    if volume_mm3 is None:
        return err_payload("volume_mm3 is required", "BAD_ARGS")
    try:
        volume_mm3 = float(volume_mm3)
    except (TypeError, ValueError):
        return err_payload("volume_mm3 must be a number", "BAD_ARGS")
    if volume_mm3 <= 0:
        return err_payload(f"volume_mm3 must be positive, got {volume_mm3}", "BAD_ARGS")

    # -- metal / density ------------------------------------------------------
    metal = a.get("metal")
    density_g_cm3 = a.get("density_g_cm3")

    if metal is not None:
        metal = str(metal).strip().lower()
        if metal not in METAL_DENSITY_G_CM3:
            valid = ", ".join(sorted(METAL_DENSITY_G_CM3.keys()))
            return err_payload(
                f"Unknown metal '{metal}'. Valid keys: {valid}", "BAD_ARGS"
            )

    if density_g_cm3 is not None:
        try:
            density_g_cm3 = float(density_g_cm3)
        except (TypeError, ValueError):
            return err_payload("density_g_cm3 must be a number", "BAD_ARGS")
        if density_g_cm3 <= 0:
            return err_payload(
                f"density_g_cm3 must be positive, got {density_g_cm3}", "BAD_ARGS"
            )

    if metal is None and density_g_cm3 is None:
        return err_payload("Either metal or density_g_cm3 must be provided", "BAD_ARGS")

    # -- optional numeric args ------------------------------------------------
    metal_price_per_gram = a.get("metal_price_per_gram", 0.0)
    labor = a.get("labor", 0.0)
    finishing = a.get("finishing", 0.0)
    casting_allowance_pct = a.get("casting_allowance_pct", 15.0)

    for name, val in [
        ("metal_price_per_gram", metal_price_per_gram),
        ("labor", labor),
        ("finishing", finishing),
        ("casting_allowance_pct", casting_allowance_pct),
    ]:
        try:
            val_f = float(val)
        except (TypeError, ValueError):
            return err_payload(f"{name} must be a number", "BAD_ARGS")
        if val_f < 0:
            return err_payload(f"{name} must be >= 0, got {val_f}", "BAD_ARGS")

    metal_price_per_gram = float(metal_price_per_gram)
    labor = float(labor)
    finishing = float(finishing)
    casting_allowance_pct = float(casting_allowance_pct)

    # -- primary estimate -----------------------------------------------------
    try:
        estimate = casting_cost(
            volume_mm3=volume_mm3,
            metal=metal,
            density_g_cm3=density_g_cm3,
            metal_price_per_gram=metal_price_per_gram,
            labor=labor,
            finishing=finishing,
            casting_allowance_pct=casting_allowance_pct,
        )
    except ValueError as exc:
        return err_payload(str(exc), "BAD_ARGS")
    except Exception as exc:
        return err_payload(f"calculation error: {exc}", "ERROR")

    estimate["label"] = METAL_LABELS.get(metal or "", metal or "custom density")

    payload: dict = {"estimate": estimate}

    # -- optional multi-metal comparison --------------------------------------
    compare_metals = a.get("compare_metals")
    if compare_metals is not None:
        if not isinstance(compare_metals, list):
            return err_payload("compare_metals must be an array", "BAD_ARGS")
        unknown = [m for m in compare_metals if m not in METAL_DENSITY_G_CM3]
        if unknown:
            valid = ", ".join(sorted(METAL_DENSITY_G_CM3.keys()))
            return err_payload(
                f"Unknown metals in compare_metals: {unknown}. Valid: {valid}",
                "BAD_ARGS",
            )
        compare_prices = a.get("compare_prices") or {}
        try:
            comparison = multi_metal_compare(
                volume_mm3=volume_mm3,
                metals=compare_metals,
                metal_prices=compare_prices,
                labor=labor,
                finishing=finishing,
                casting_allowance_pct=casting_allowance_pct,
            )
        except ValueError as exc:
            return err_payload(str(exc), "BAD_ARGS")
        except Exception as exc:
            return err_payload(f"comparison error: {exc}", "ERROR")
        payload["comparison"] = comparison

    return ok_payload(payload)
