"""
kerf_cad_core.marine.tools — LLM tool wrappers for marine hull design.

Registers three tools with the Kerf tool registry:

  marine_hull_from_offsets
      Build a lofted control-net recipe from a half-breadth offset table.
      Returns the parametric recipe (op="marine_loft_hull") plus principal
      dimensions.

  marine_fairing_report
      Compute hull fairing quality metrics: curvature monotonicity per
      station, batten/spline bending energy, and longitudinal roughness.

  marine_hydrostatics
      Compute waterplane area, displaced volume, and LCB via Simpson's rule.

All tools are pure-Python; no OCC dependency.
Inputs are validated and errors returned as {ok: false, errors: [...]} —
tools never raise.

Units: metres (m), metres² (m²), metres³ (m³) throughout.

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.marine.hull import (
    hull_from_offsets,
    fairing_report,
    hydrostatics,
    faired_hull_surface,
)

# ---------------------------------------------------------------------------
# Shared schema fragment
# ---------------------------------------------------------------------------

_OFFSETS_SCHEMA = {
    "type": "array",
    "description": (
        "Table of half-breadth offsets.  Each entry is an object with:\n"
        "  station (number)      — longitudinal position in metres "
        "(0 = bow, increasing to stern)\n"
        "  waterline (number)    — vertical position in metres "
        "(0 = keel baseline, increasing upward)\n"
        "  half_breadth (number) — half-beam (port or starboard) at that "
        "station/waterline in metres (>= 0)\n"
        "Minimum 3 rows required; at least 2 distinct stations and 2 distinct "
        "waterlines.  Duplicate (station, waterline) pairs are rejected."
    ),
    "items": {
        "type": "object",
        "properties": {
            "station":      {"type": "number"},
            "waterline":    {"type": "number"},
            "half_breadth": {"type": "number"},
        },
        "required": ["station", "waterline", "half_breadth"],
    },
}


# ---------------------------------------------------------------------------
# Tool: marine_hull_from_offsets
# ---------------------------------------------------------------------------

_hull_spec = ToolSpec(
    name="marine_hull_from_offsets",
    description=(
        "Build a parametric NURBS-loft hull recipe from a table of half-breadths "
        "(offset table).\n"
        "\n"
        "Input: a list of {station, waterline, half_breadth} rows (metres).\n"
        "  station      — longitudinal X position (0=bow, increasing to stern)\n"
        "  waterline    — vertical Z position (0=keel, increasing upward)\n"
        "  half_breadth — half-beam at that station/waterline (>= 0)\n"
        "\n"
        "Output: {ok, op, stations, waterlines, sections, knot_params, loa, "
        "max_half_beam, depth, station_count, waterline_count}.\n"
        "\n"
        "The returned recipe (op='marine_loft_hull') is pure parametric data; "
        "a downstream NURBS worker uses it to produce the actual surface.  "
        "Pass it to marine_fairing_report or marine_hydrostatics for analysis.\n"
        "\n"
        "Errors returned as {ok: false, errors: [...]} for malformed tables.  "
        "Never raises.\n"
        "\n"
        "Typical workflow:\n"
        "  1. marine_hull_from_offsets(offsets=...) → recipe + dimensions\n"
        "  2. marine_fairing_report(offsets=...)    → quality metrics\n"
        "  3. marine_hydrostatics(offsets=...)      → Awp, ∇, LCB"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "offsets": _OFFSETS_SCHEMA,
        },
        "required": ["offsets"],
    },
)


@register(_hull_spec, write=False)
async def run_marine_hull_from_offsets(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    offsets = a.get("offsets")
    if offsets is None:
        return json.dumps({"ok": False, "errors": ["'offsets' field is required"]})

    result = hull_from_offsets(offsets)
    if not result.get("ok"):
        return json.dumps(result)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: marine_fairing_report
# ---------------------------------------------------------------------------

_fairing_spec = ToolSpec(
    name="marine_fairing_report",
    description=(
        "Compute hull fairing quality metrics for a half-breadth offset table.\n"
        "\n"
        "Three metrics are reported:\n"
        "\n"
        "1. curvature_monotonicity (per station)\n"
        "   Checks that the half-breadth profile at each station is convex: "
        "non-decreasing from keel to max-breadth waterline, non-increasing above "
        "it.  A 'kink' is flagged when the sign of consecutive differences changes "
        "more than once (inflection point not attributable to beam turnover).\n"
        "\n"
        "2. batten_energy (per station)\n"
        "   Approximate bending energy (m³) of a natural cubic spline fit to "
        "the WL→Y profile at each station.  Lower energy = fairer curve.  "
        "Analogous to a physical batten resisting bending.\n"
        "\n"
        "3. roughness_per_waterline (longitudinal)\n"
        "   RMS of second finite differences of half-breadths along each "
        "waterline.  Measures fairness in the longitudinal (station) direction.  "
        "0.0 on a perfectly fair hull.\n"
        "\n"
        "overall_roughness: mean of all per-waterline RMS values.\n"
        "\n"
        "Errors returned as {ok: false, errors: [...]}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "offsets": _OFFSETS_SCHEMA,
        },
        "required": ["offsets"],
    },
)


@register(_fairing_spec, write=False)
async def run_marine_fairing_report(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    offsets = a.get("offsets")
    if offsets is None:
        return json.dumps({"ok": False, "errors": ["'offsets' field is required"]})

    result = fairing_report(offsets)
    if not result.get("ok"):
        return json.dumps(result)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: marine_hydrostatics
# ---------------------------------------------------------------------------

_hydro_spec = ToolSpec(
    name="marine_hydrostatics",
    description=(
        "Compute basic hydrostatic properties from a hull half-breadth offset table.\n"
        "\n"
        "Method: composite Simpson's 1/3 rule — exact for polynomials up to degree 3.  "
        "Reference: D. J. Eyres, Ship Stability for Masters and Mates, Chapter 6.\n"
        "\n"
        "Quantities\n"
        "----------\n"
        "waterplane_area_m2\n"
        "    Awp = ∫₀^L 2·y(x,T) dx  [m²]\n"
        "    Area of the waterplane at the design waterline T.\n"
        "\n"
        "displaced_volume_m3\n"
        "    ∇ = ∫₀^L Aₓ(x) dx  [m³]\n"
        "    Displaced volume below the design waterline.\n"
        "    For a rectangular box barge (length L, beam B, draft T):\n"
        "        ∇ = L × B × T  (verified by Simpson's rule for constant offsets)\n"
        "\n"
        "lcb_from_bow_m\n"
        "    LCB = (1/∇) · ∫₀^L x·Aₓ(x) dx  [m from bow]\n"
        "    Longitudinal Centre of Buoyancy measured from the first station.\n"
        "\n"
        "Parameters\n"
        "----------\n"
        "offsets          — half-breadth offset table\n"
        "design_waterline — optional float (metres); defaults to max WL in table\n"
        "\n"
        "Errors returned as {ok: false, errors: [...]}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "offsets": _OFFSETS_SCHEMA,
            "design_waterline": {
                "type": "number",
                "description": (
                    "Design waterline (draft) in metres.  Optional; defaults to "
                    "the maximum waterline in the offset table."
                ),
            },
        },
        "required": ["offsets"],
    },
)


@register(_hydro_spec, write=False)
async def run_marine_hydrostatics(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    offsets = a.get("offsets")
    if offsets is None:
        return json.dumps({"ok": False, "errors": ["'offsets' field is required"]})

    design_wl = a.get("design_waterline")  # may be None

    result = hydrostatics(offsets, design_waterline=design_wl)
    if not result.get("ok"):
        return json.dumps(result)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: marine_hull_fair_surface
# ---------------------------------------------------------------------------

_fair_surface_spec = ToolSpec(
    name="marine_hull_fair_surface",
    description=(
        "Build a faired NURBS hull surface from a table of half-breadths and "
        "attach curvature-comb analysis.\n"
        "\n"
        "Fairing workflow:\n"
        "  1. Fit a natural cubic spline (minimum bending energy) through each\n"
        "     station's waterline → half-breadth profile and re-evaluate it at\n"
        "     the original waterline positions (transverse fairing).\n"
        "  2. Repeat across stations at each waterline (longitudinal fairing).\n"
        "  3. Repeat for `fairing_passes` iterations (default 1; 2 passes for\n"
        "     high-curvature hulls).\n"
        "  4. Build a degree-3 × degree-3 NURBS surface from the faired grid.\n"
        "  5. Sample principal curvatures (k1/k2, mean H, Gaussian K) on a UV\n"
        "     grid via GeomLProp_SLProps-equivalent Python code, producing a\n"
        "     `curvature_combs` payload consumed by `CurvatureCombOverlay.jsx`.\n"
        "\n"
        "Returns:\n"
        "  nurbs_surface    — degree/knot/control-point data for the faired surface\n"
        "  curvature_combs  — sampled k1/k2/H/K + sample points for the viewport\n"
        "  fairness_metrics — monotonicity, batten energy improvement, roughness\n"
        "\n"
        "Use marine_fairing_report to inspect the raw (unfaired) offsets first.\n"
        "Errors returned as {ok: false, errors: [...]}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "offsets": _OFFSETS_SCHEMA,
            "uv_density": {
                "type": "number",
                "description": (
                    "UV grid step for curvature-comb sampling as a fraction of "
                    "the parameter range (default 0.1 → ~10×10 grid). "
                    "Range: 0.01–0.5."
                ),
            },
            "scale_factor": {
                "type": "number",
                "description": (
                    "Comb line length multiplier (default 10). "
                    "Increase for nearly-flat surfaces; decrease for high-curvature ones."
                ),
            },
            "fairing_passes": {
                "type": "integer",
                "description": (
                    "Number of transverse + longitudinal fairing iterations "
                    "(default 1). Use 2–3 for irregular or high-curvature hulls."
                ),
            },
        },
        "required": ["offsets"],
    },
)


@register(_fair_surface_spec, write=False)
async def run_marine_hull_fair_surface(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    offsets = a.get("offsets")
    if offsets is None:
        return json.dumps({"ok": False, "errors": ["'offsets' field is required"]})

    uv_density = a.get("uv_density", 0.1)
    scale_factor = a.get("scale_factor", 10.0)
    fairing_passes = a.get("fairing_passes", 1)

    result = faired_hull_surface(
        offsets,
        uv_density=uv_density,
        scale_factor=scale_factor,
        fairing_passes=fairing_passes,
    )
    if not result.get("ok"):
        return json.dumps(result)
    return ok_payload(result)
