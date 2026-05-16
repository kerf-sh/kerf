"""
kerf_cad_core.packaging.tools — LLM tool wrappers for protective-packaging & shipping design.

Registers seven tools with the Kerf tool registry:

  pkg_box_compression_strength — McKee BCT, safety factor, stack-overload check
  pkg_pallet_pattern           — column vs interlock optimisation, cube/area utilisation
  pkg_shipping_weight          — DIM weight, chargeable weight, NMFC freight class
  pkg_cushion_design           — drop height → cushion thickness, fragility checks
  pkg_shock_transmissibility   — single-DOF transmissibility through cushion
  pkg_container_fill           — ISO container (20GP/40GP/40HC/45HC) case-count optimisation
  pkg_stretch_wrap             — containment force & EUMOS 40509 compliance

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
McKee, R.C. (1963) — Box Compression: A Simple Formula.
TAPPI T804 — Compression Test of Fiberboard Shipping Containers.
ASTM D1596 — Shock-Absorbing Characteristics of Packaging Material.
ISTA 2A/2B — Packaged-Product Performance Testing.
EUMOS 40509 — Test Method for Unitised Loads; Containment Force.
NMFC Item 360 — Freight Classification by Density.
ISO 668:2020 — Series 1 Freight Containers — Classification.

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.packaging.design import (
    box_compression_strength,
    pallet_pattern,
    shipping_weight,
    cushion_design,
    shock_transmissibility,
    container_fill,
    stretch_wrap,
)


# ---------------------------------------------------------------------------
# Tool: pkg_box_compression_strength
# ---------------------------------------------------------------------------

_box_compression_spec = ToolSpec(
    name="pkg_box_compression_strength",
    description=(
        "Compute corrugated-box compression strength using the McKee formula and "
        "check against a warehouse stack load.\n"
        "\n"
        "McKee formula: BCT = C_f × ECT × (Z × t)^0.5\n"
        "where ECT is edge-crush test (N/m), C_f is McKee constant (~5.874 SI), "
        "Z is box perimeter (mm), t is board thickness from flute table.\n"
        "\n"
        "Derating: BCT_derated = BCT × humidity_factor × time_factor.\n"
        "Allowable  = BCT_derated / safety_factor.\n"
        "\n"
        "Flags: stack_overload when allowable < stack_load_N.\n"
        "\n"
        "Flute options: A, B, C (default), E, F, BC, EB.\n"
        "\n"
        "Returns: BCT_N, BCT_derated_N, allowable_N, board_thickness_mm, "
        "stack_overload (if stack_load_N given), warnings.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "ECT": {
                "type": "number",
                "description": (
                    "Edge-crush test value (N/m). "
                    "Typical C-flute single-wall: 3500–7000 N/m. Must be > 0."
                ),
            },
            "C_f": {
                "type": "number",
                "description": (
                    "McKee constant (dimensionless). Typical SI value: 5.874. Must be > 0."
                ),
            },
            "Z": {
                "type": "number",
                "description": "Box perimeter (mm). Must be > 0.",
            },
            "safety_factor": {
                "type": "number",
                "description": "Safety factor >= 1.0. TAPPI recommends >= 1.5 (default 1.0).",
            },
            "humidity_factor": {
                "type": "number",
                "description": (
                    "Humidity derate factor (0–1). "
                    "0.60–0.80 for high-humidity warehouse. Default 1.0 (dry)."
                ),
            },
            "time_factor": {
                "type": "number",
                "description": (
                    "Long-term creep derate factor (0–1). "
                    "0.50 for 30-day storage. Default 1.0 (short-term)."
                ),
            },
            "stack_load_N": {
                "type": "number",
                "description": (
                    "Actual warehouse stack load (N). Optional. "
                    "If given, checks allowable >= stack_load_N."
                ),
            },
            "flute": {
                "type": "string",
                "enum": ["A", "B", "C", "E", "F", "BC", "EB"],
                "description": "Flute type for board thickness lookup. Default 'C'.",
            },
        },
        "required": ["ECT", "C_f", "Z"],
    },
)


@register(_box_compression_spec, write=False)
async def run_box_compression_strength(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("ECT", "C_f", "Z"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("safety_factor", "humidity_factor", "time_factor",
                "stack_load_N", "flute"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = box_compression_strength(a["ECT"], a["C_f"], a["Z"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pkg_pallet_pattern
# ---------------------------------------------------------------------------

_pallet_pattern_spec = ToolSpec(
    name="pkg_pallet_pattern",
    description=(
        "Optimise pallet loading for column-stack or interlocked (brick) patterns.\n"
        "\n"
        "Tries column (identical orientation every layer) and interlock (90° rotation "
        "on alternate layers) and returns the best arrangement by cases_per_pallet.\n"
        "\n"
        "Returns: pattern_used, cases_per_layer, layers, cases_per_pallet, "
        "area_utilisation, cube_utilisation, pallet_weight_kg (if case_weight_kg given), "
        "warnings.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "case_L": {"type": "number", "description": "Case length (mm). Must be > 0."},
            "case_W": {"type": "number", "description": "Case width (mm). Must be > 0."},
            "case_H": {"type": "number", "description": "Case height (mm). Must be > 0."},
            "pallet_L": {"type": "number", "description": "Pallet deck length (mm). Must be > 0."},
            "pallet_W": {"type": "number", "description": "Pallet deck width (mm). Must be > 0."},
            "max_height": {
                "type": "number",
                "description": (
                    "Maximum loaded pallet height including deck (mm). Must be > 0. "
                    "Typical: 2200 mm for most transport modes."
                ),
            },
            "pattern": {
                "type": "string",
                "enum": ["column", "interlock", "auto"],
                "description": (
                    "Pallet pattern: 'column', 'interlock', or 'auto' (default). "
                    "'auto' tries both and picks the highest case count."
                ),
            },
            "case_weight_kg": {
                "type": "number",
                "description": (
                    "Gross case weight (kg). Optional. If given, pallet_weight_kg is returned."
                ),
            },
            "max_pallet_kg": {
                "type": "number",
                "description": (
                    "Maximum gross pallet weight (kg). Optional. Caps layers to avoid overweight."
                ),
            },
        },
        "required": ["case_L", "case_W", "case_H", "pallet_L", "pallet_W", "max_height"],
    },
)


@register(_pallet_pattern_spec, write=False)
async def run_pallet_pattern(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("case_L", "case_W", "case_H", "pallet_L", "pallet_W", "max_height"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("pattern", "case_weight_kg", "max_pallet_kg"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = pallet_pattern(
        a["case_L"], a["case_W"], a["case_H"],
        a["pallet_L"], a["pallet_W"], a["max_height"],
        **kwargs,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pkg_shipping_weight
# ---------------------------------------------------------------------------

_shipping_weight_spec = ToolSpec(
    name="pkg_shipping_weight",
    description=(
        "Compute dimensional (volumetric) weight, chargeable weight, and NMFC "
        "freight class for a carton.\n"
        "\n"
        "DIM weight = volume_cm³ / DIM_factor\n"
        "  DIM_factor = 5000 cm³/kg domestic courier; 6000 international.\n"
        "Chargeable weight = max(actual_kg, DIM weight).\n"
        "\n"
        "NMFC freight class is looked up from density (lb/ft³) per NMFC Item 360.\n"
        "\n"
        "Returns: volume_cm3, dim_weight_kg, chargeable_weight_kg, dim_factor, "
        "density_lb_ft3, freight_class, warnings.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "length_mm": {"type": "number", "description": "Carton length (mm). Must be > 0."},
            "width_mm": {"type": "number", "description": "Carton width (mm). Must be > 0."},
            "height_mm": {"type": "number", "description": "Carton height (mm). Must be > 0."},
            "actual_kg": {
                "type": "number",
                "description": "Actual gross weight (kg). Must be > 0.",
            },
            "carrier": {
                "type": "string",
                "enum": ["domestic", "international"],
                "description": (
                    "Carrier type: 'domestic' (DIM factor 5000) or "
                    "'international' (DIM factor 6000). Default 'domestic'."
                ),
            },
            "freight_class_override": {
                "type": "number",
                "description": (
                    "Override NMFC class lookup (optional). "
                    "Standard classes: 50, 55, 60, 65, 70, 77.5, 85, 92.5, 100, "
                    "110, 125, 150, 175, 200, 250, 300, 400, 500."
                ),
            },
        },
        "required": ["length_mm", "width_mm", "height_mm", "actual_kg"],
    },
)


@register(_shipping_weight_spec, write=False)
async def run_shipping_weight(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("length_mm", "width_mm", "height_mm", "actual_kg"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("carrier", "freight_class_override"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = shipping_weight(
        a["length_mm"], a["width_mm"], a["height_mm"], a["actual_kg"], **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pkg_cushion_design
# ---------------------------------------------------------------------------

_cushion_design_spec = ToolSpec(
    name="pkg_cushion_design",
    description=(
        "Design protective-foam cushion from drop height, product fragility, "
        "and foam cushion-curve data per ASTM D1596 / ISTA.\n"
        "\n"
        "Method:\n"
        "  ΔV = √(2 g h)                            (velocity change from drop height)\n"
        "  σ_static = weight / bearing_area          (static stress on foam)\n"
        "  G_allow  = fragility_G / safety_factor\n"
        "  t_cushion = ΔV² / (2 × G_allow × g)      (energy method)\n"
        "\n"
        "Flags:\n"
        "  under_cushioned  — foam cushion-curve G > fragility_G\n"
        "  fragile_exceeded — foam cushion-curve G > G_allow\n"
        "\n"
        "Returns: delta_V_m_s, static_stress_kPa, required_thickness_mm, G_allow, "
        "under_cushioned, fragile_exceeded, warnings.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "product_weight_kg": {
                "type": "number",
                "description": "Product gross weight (kg). Must be > 0.",
            },
            "drop_height_m": {
                "type": "number",
                "description": (
                    "Drop height (m) per ISTA test procedure. Must be > 0. "
                    "Typical values: 0.3 m (light parcel) to 1.0 m (pallet)."
                ),
            },
            "fragility_G": {
                "type": "number",
                "description": (
                    "Product fragility (peak G tolerable). Must be > 1. "
                    "Typical electronics: 40–100G; precision instruments: 15–30G."
                ),
            },
            "foam_static_stress_kPa": {
                "type": "number",
                "description": (
                    "Static stress on foam (kPa) at the operating bearing area. "
                    "Used to cross-check cushion curve. Must be > 0."
                ),
            },
            "foam_cushion_curve_G": {
                "type": "number",
                "description": (
                    "Peak G value read from foam cushion curve at the operating "
                    "static stress and required thickness. Must be > 0."
                ),
            },
            "bearing_area_cm2": {
                "type": "number",
                "description": (
                    "Foam bearing area (cm²). Default 100 cm². Must be > 0."
                ),
            },
            "safety_factor": {
                "type": "number",
                "description": (
                    "Safety factor on fragility_G. G_allow = fragility_G / SF. "
                    "Must be >= 1.0. Default 1.5."
                ),
            },
        },
        "required": [
            "product_weight_kg", "drop_height_m", "fragility_G",
            "foam_static_stress_kPa", "foam_cushion_curve_G",
        ],
    },
)


@register(_cushion_design_spec, write=False)
async def run_cushion_design(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("product_weight_kg", "drop_height_m", "fragility_G",
                  "foam_static_stress_kPa", "foam_cushion_curve_G"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("bearing_area_cm2", "safety_factor"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = cushion_design(
        a["product_weight_kg"], a["drop_height_m"], a["fragility_G"],
        a["foam_static_stress_kPa"], a["foam_cushion_curve_G"],
        **kwargs,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pkg_shock_transmissibility
# ---------------------------------------------------------------------------

_shock_transmissibility_spec = ToolSpec(
    name="pkg_shock_transmissibility",
    description=(
        "Compute single-DOF shock & vibration transmissibility through a packaging cushion.\n"
        "\n"
        "  T = √( (1 + (2ζr)²) / ((1-r²)² + (2ζr)²) )\n"
        "  r = input_freq_Hz / fn_Hz   (frequency ratio)\n"
        "\n"
        "T > 1 → cushion amplifies; T < 1 → cushion isolates.\n"
        "Isolation only for r > √2 ≈ 1.41.\n"
        "\n"
        "Returns: frequency_ratio, transmissibility, attenuation_dB, "
        "isolation_pct, resonance_warning, warnings.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "fn_Hz": {
                "type": "number",
                "description": (
                    "Natural frequency of packaged product on cushion (Hz). Must be > 0. "
                    "Typical packaging system: 2–20 Hz."
                ),
            },
            "damping_ratio": {
                "type": "number",
                "description": (
                    "Damping ratio ζ (0 < ζ < 1). "
                    "Foam packaging: 0.05–0.20. Must be > 0 and < 1."
                ),
            },
            "input_freq_Hz": {
                "type": "number",
                "description": (
                    "Excitation / input frequency (Hz). Must be > 0. "
                    "Road transport: 1–10 Hz; air freight: 5–50 Hz."
                ),
            },
        },
        "required": ["fn_Hz", "damping_ratio", "input_freq_Hz"],
    },
)


@register(_shock_transmissibility_spec, write=False)
async def run_shock_transmissibility(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("fn_Hz", "damping_ratio", "input_freq_Hz"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = shock_transmissibility(
        a["fn_Hz"], a["damping_ratio"], a["input_freq_Hz"]
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pkg_container_fill
# ---------------------------------------------------------------------------

_container_fill_spec = ToolSpec(
    name="pkg_container_fill",
    description=(
        "Optimise case-count in an ISO shipping container (20GP / 40GP / 40HC / 45HC).\n"
        "\n"
        "Tries all 6 box orientations (permutations of L/W/H) unless "
        "orientation_permutations=false, and returns the arrangement with the "
        "highest volume utilisation.\n"
        "\n"
        "Returns: container_type, internal dimensions, orientation_used, "
        "cases_per_row, cases_per_col, layers, total_cases, volume_utilisation, "
        "warnings.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "case_L": {"type": "number", "description": "Case length (mm). Must be > 0."},
            "case_W": {"type": "number", "description": "Case width (mm). Must be > 0."},
            "case_H": {"type": "number", "description": "Case height (mm). Must be > 0."},
            "container_type": {
                "type": "string",
                "enum": ["20GP", "40GP", "40HC", "45HC"],
                "description": (
                    "ISO container type. "
                    "20GP: 5898×2352×2393 mm; "
                    "40GP: 12025×2352×2393 mm; "
                    "40HC: 12025×2352×2698 mm; "
                    "45HC: 13556×2352×2698 mm. "
                    "Default '40GP'."
                ),
            },
            "orientation_permutations": {
                "type": "boolean",
                "description": (
                    "If true (default), try all 6 box orientations; "
                    "if false, use input order only."
                ),
            },
        },
        "required": ["case_L", "case_W", "case_H"],
    },
)


@register(_container_fill_spec, write=False)
async def run_container_fill(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("case_L", "case_W", "case_H"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("container_type", "orientation_permutations"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = container_fill(a["case_L"], a["case_W"], a["case_H"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pkg_stretch_wrap
# ---------------------------------------------------------------------------

_stretch_wrap_spec = ToolSpec(
    name="pkg_stretch_wrap",
    description=(
        "Compute stretch-wrap containment force and check EUMOS 40509 compliance.\n"
        "\n"
        "Containment force (empirical LLDPE model):\n"
        "  F_per_rev = k_film × gauge_μm × pre_stretch_ratio × overlap × 2 × perimeter\n"
        "  F_total   = F_per_rev × revolutions\n"
        "\n"
        "EUMOS 40509 class-1 minimum:\n"
        "  F_min = 0.4 × pallet_weight_kg × 9.81  (N)\n"
        "\n"
        "Also returns revolutions_for_minimum — minimum revolutions to meet EUMOS.\n"
        "\n"
        "Returns: F_per_revolution_N, F_total_N, F_min_required_N, eumos_compliant, "
        "revolutions_for_minimum, warnings.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "pallet_weight_kg": {
                "type": "number",
                "description": "Gross pallet weight, product + deck (kg). Must be > 0.",
            },
            "film_gauge_um": {
                "type": "number",
                "description": (
                    "Stretch film gauge (μm). Typical: 17–30 μm. Must be > 0."
                ),
            },
            "revolutions": {
                "type": "integer",
                "description": "Number of wrap revolutions. Must be >= 1. Default 3.",
            },
            "overlap_fraction": {
                "type": "number",
                "description": (
                    "Fraction of film width overlapping per revolution (0–1). Default 0.50."
                ),
            },
            "pre_stretch_pct": {
                "type": "number",
                "description": (
                    "Pre-stretch percentage by wrap machine (%). "
                    "Typical: 150–300%. Default 200%."
                ),
            },
        },
        "required": ["pallet_weight_kg", "film_gauge_um"],
    },
)


@register(_stretch_wrap_spec, write=False)
async def run_stretch_wrap(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("pallet_weight_kg", "film_gauge_um"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("revolutions", "overlap_fraction", "pre_stretch_pct"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = stretch_wrap(a["pallet_weight_kg"], a["film_gauge_um"], **kwargs)
    return ok_payload(result)
