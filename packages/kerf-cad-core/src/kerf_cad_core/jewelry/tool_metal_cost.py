"""
jewelry_metal_cost LLM tool
============================

Registers the `jewelry_metal_cost` tool with the Kerf tool registry.
The tool computes metal weight, casting weight, itemised casting cost,
gemstone cost, labour/setting/finishing, and a full jeweller's quote
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
    METAL_PRICE_PRESETS,
    casting_cost,
    jewelry_quote,
    multi_metal_compare,
)

# ---------------------------------------------------------------------------
# Tool spec
# ---------------------------------------------------------------------------

jewelry_metal_cost_spec = ToolSpec(
    name="jewelry_metal_cost",
    description=(
        "Estimate metal weight and casting cost for a jewelry piece, with optional "
        "gemstone cost, labour, setting fees, finishing, and a full jeweller's quote.\n"
        "\n"
        "Given a part volume (in mm³) and metal selection, returns:\n"
        "  - net weight (g / dwt / ozt)\n"
        "  - casting gross weight with sprue/button/flashing allowance\n"
        "  - itemised stone cost line items (if stones provided)\n"
        "  - labour, setting, and finishing costs\n"
        "  - full quote breakdown with configurable markup\n"
        "  - optional multi-metal comparison table\n"
        "\n"
        "Volume can be entered manually or read from a OCCT volume query "
        "(GProp_GProps.Mass() in mm model units). Metal price is a user "
        "input — no live feed. Use spot gold/silver prices as a baseline "
        "and add your supplier's premium. Alternatively supply a price_preset "
        "name (e.g. 'usd_2024_approx') for orientation-only defaults.\n"
        "\n"
        "Valid metal keys (pass as `metal`):\n"
        "  Gold:      10k_yellow, 14k_yellow, 18k_yellow, 22k_yellow, 24k_yellow\n"
        "             10k_white,  14k_white,  18k_white,  22k_white\n"
        "             10k_rose,   14k_rose,   18k_rose,   22k_rose\n"
        "  Platinum:  platinum_950, platinum_900\n"
        "  Palladium: palladium_950, palladium_500\n"
        "  Silver:    sterling_925, fine_silver, argentium_935\n"
        "  Other:     titanium, brass, bronze\n"
        "\n"
        "Stone specs (for stones list):\n"
        "  cut, carat (or mm), price_per_carat, count, note\n"
        "  Carat can come directly from the gemstones tool output.\n"
        "\n"
        "Setting types: prong, bezel, pave, channel, flush, invisible, tension, bar\n"
        "Finishing types: polish, satin, hammer, rhodium, black_rhodium, "
        "gold_plate, antique, sandblast"
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
                    "(varies daily; check your supplier). Default 0. "
                    "Overrides price_preset when non-zero."
                ),
            },
            "price_preset": {
                "type": "string",
                "description": (
                    "Named price preset for orientation defaults. "
                    "Currently available: 'usd_2024_approx'. "
                    "Only used when metal_price_per_gram is 0. "
                    "These are NOT live prices — always verify with your supplier."
                ),
            },
            "casting_allowance_pct": {
                "type": "number",
                "description": (
                    "Sprue / button / flashing overhead as a percentage of net weight. "
                    "Default 15. Typical range 10 (optimised gate) – 25 (complex mould)."
                ),
            },
            "stones": {
                "type": "array",
                "description": (
                    "Optional list of stone specs for gemstone cost line items. "
                    "Each item: {cut, carat (or mm), price_per_carat, count, note}. "
                    "Carat can come from the gemstones tool output. "
                    "Do not use if there are no stones."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "cut":             {"type": "string"},
                        "carat":           {"type": "number"},
                        "mm":              {"type": "number"},
                        "price_per_carat": {"type": "number"},
                        "count":           {"type": "integer"},
                        "note":            {"type": "string"},
                    },
                    "required": ["price_per_carat"],
                },
            },
            "bench_hours": {
                "type": "number",
                "description": "Bench labour hours. Default 0.",
            },
            "hourly_rate": {
                "type": "number",
                "description": "Bench hourly rate in your currency. Default 0.",
            },
            "setting_type": {
                "type": "string",
                "description": (
                    "Stone setting style: prong, bezel, pave, channel, flush, "
                    "invisible, tension, bar. Default 'prong'."
                ),
            },
            "setting_fee_per_stone": {
                "type": "number",
                "description": (
                    "Override per-stone setting fee. "
                    "If absent, uses the default fee for setting_type."
                ),
            },
            "finishing_type": {
                "type": "string",
                "description": (
                    "Named finishing: polish, satin, hammer, rhodium, black_rhodium, "
                    "gold_plate, antique, sandblast. "
                    "If absent, no finishing charge is added."
                ),
            },
            "finishing_cost": {
                "type": "number",
                "description": "Explicit finishing cost override (overrides finishing_type default).",
            },
            "markup_pct": {
                "type": "number",
                "description": (
                    "Markup percentage applied to subtotal (e.g. 20 = +20%). "
                    "Default 0 (no markup). Must be >= 0."
                ),
            },
            "labor": {
                "type": "number",
                "description": (
                    "Legacy flat bench labor cost (casting + cleanup + polish). "
                    "Use bench_hours + hourly_rate for the full parametric model. "
                    "When both are supplied, bench_hours × hourly_rate is used and "
                    "labor is ignored for the full quote."
                ),
            },
            "finishing": {
                "type": "number",
                "description": (
                    "Legacy flat finishing / plating / rhodium cost. "
                    "Use finishing_type or finishing_cost for the parametric model."
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

    # -- price preset ---------------------------------------------------------
    price_preset = a.get("price_preset")
    if price_preset is not None and price_preset not in METAL_PRICE_PRESETS:
        return err_payload(
            f"Unknown price_preset '{price_preset}'. Valid: {sorted(METAL_PRICE_PRESETS)}",
            "BAD_ARGS",
        )

    # -- optional numeric args ------------------------------------------------
    metal_price_per_gram = a.get("metal_price_per_gram", 0.0)
    casting_allowance_pct = a.get("casting_allowance_pct", 15.0)
    markup_pct = a.get("markup_pct", 0.0)

    for name, val in [
        ("metal_price_per_gram", metal_price_per_gram),
        ("casting_allowance_pct", casting_allowance_pct),
        ("markup_pct", markup_pct),
    ]:
        try:
            val_f = float(val)
        except (TypeError, ValueError):
            return err_payload(f"{name} must be a number", "BAD_ARGS")
        if val_f < 0:
            return err_payload(f"{name} must be >= 0, got {val_f}", "BAD_ARGS")

    metal_price_per_gram = float(metal_price_per_gram)
    casting_allowance_pct = float(casting_allowance_pct)
    markup_pct = float(markup_pct)

    # Legacy flat labor/finishing (for backwards compatibility with casting_cost path)
    labor = a.get("labor", 0.0)
    finishing_flat = a.get("finishing", 0.0)
    for name, val in [("labor", labor), ("finishing", finishing_flat)]:
        try:
            val_f = float(val)
        except (TypeError, ValueError):
            return err_payload(f"{name} must be a number", "BAD_ARGS")
        if val_f < 0:
            return err_payload(f"{name} must be >= 0, got {val_f}", "BAD_ARGS")
    labor = float(labor)
    finishing_flat = float(finishing_flat)

    # -- parametric labour args -----------------------------------------------
    bench_hours = float(a.get("bench_hours", 0.0))
    hourly_rate = float(a.get("hourly_rate", 0.0))
    setting_type = str(a.get("setting_type", "prong"))
    setting_fee_per_stone = a.get("setting_fee_per_stone")
    if setting_fee_per_stone is not None:
        try:
            setting_fee_per_stone = float(setting_fee_per_stone)
        except (TypeError, ValueError):
            return err_payload("setting_fee_per_stone must be a number", "BAD_ARGS")
        if setting_fee_per_stone < 0:
            return err_payload(
                f"setting_fee_per_stone must be >= 0, got {setting_fee_per_stone}", "BAD_ARGS"
            )

    finishing_type = a.get("finishing_type")
    finishing_cost_override = a.get("finishing_cost")
    if finishing_cost_override is not None:
        try:
            finishing_cost_override = float(finishing_cost_override)
        except (TypeError, ValueError):
            return err_payload("finishing_cost must be a number", "BAD_ARGS")
        if finishing_cost_override < 0:
            return err_payload(
                f"finishing_cost must be >= 0, got {finishing_cost_override}", "BAD_ARGS"
            )

    # -- stones ---------------------------------------------------------------
    stones = a.get("stones")
    if stones is not None and not isinstance(stones, list):
        return err_payload("stones must be an array", "BAD_ARGS")

    # -- decide whether to use full quote or legacy casting_cost path ---------
    # Full quote path: any of the new params are set
    use_full_quote = (
        (stones and len(stones) > 0)
        or bench_hours > 0
        or markup_pct > 0
        or finishing_type is not None
        or finishing_cost_override is not None
        or price_preset is not None
    )

    if use_full_quote:
        # For the full quote, bench_hours/hourly_rate take precedence for labour.
        # If legacy labor is set and bench params aren't, convert for compatibility.
        effective_bench_hours = bench_hours
        effective_hourly_rate = hourly_rate
        effective_finishing_cost = finishing_cost_override
        if bench_hours == 0.0 and labor > 0.0:
            # Legacy: treat flat labor as a bench_hours=1, rate=labor (preserves value)
            effective_bench_hours = 1.0
            effective_hourly_rate = labor
        if finishing_cost_override is None and finishing_flat > 0.0 and finishing_type is None:
            effective_finishing_cost = finishing_flat

        try:
            quote = jewelry_quote(
                volume_mm3=volume_mm3,
                metal=metal,
                density_g_cm3=density_g_cm3,
                metal_price_per_gram=metal_price_per_gram,
                casting_allowance_pct=casting_allowance_pct,
                stones=stones,
                bench_hours=effective_bench_hours,
                hourly_rate=effective_hourly_rate,
                setting_type=setting_type,
                setting_fee_per_stone=setting_fee_per_stone,
                finishing_type=finishing_type,
                finishing_cost=effective_finishing_cost,
                markup_pct=markup_pct,
                price_preset=price_preset,
            )
        except ValueError as exc:
            return err_payload(str(exc), "BAD_ARGS")
        except Exception as exc:
            return err_payload(f"quote error: {exc}", "ERROR")

        payload: dict = {"estimate": quote, "mode": "full_quote"}

    else:
        # Legacy path: plain casting_cost + flat labor/finishing
        try:
            estimate = casting_cost(
                volume_mm3=volume_mm3,
                metal=metal,
                density_g_cm3=density_g_cm3,
                metal_price_per_gram=metal_price_per_gram,
                labor=labor,
                finishing=finishing_flat,
                casting_allowance_pct=casting_allowance_pct,
            )
        except ValueError as exc:
            return err_payload(str(exc), "BAD_ARGS")
        except Exception as exc:
            return err_payload(f"calculation error: {exc}", "ERROR")

        estimate["label"] = METAL_LABELS.get(metal or "", metal or "custom density")
        payload = {"estimate": estimate, "mode": "casting_cost"}

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
                finishing=finishing_flat,
                casting_allowance_pct=casting_allowance_pct,
            )
        except ValueError as exc:
            return err_payload(str(exc), "BAD_ARGS")
        except Exception as exc:
            return err_payload(f"comparison error: {exc}", "ERROR")
        payload["comparison"] = comparison

    return ok_payload(payload)
