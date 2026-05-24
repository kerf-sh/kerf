"""
kerf_cad_core.matsel.multi_objective_tools — LLM tool wrappers for Pareto-style
multi-objective material selection.

Registers three tools with the Kerf tool registry:

  matsel_pareto       — non-dominated Pareto-frontier for N objectives
  matsel_weighted     — linear weighted-sum multi-objective ranking
  matsel_tradeoff     — convex Pareto envelope for two-axis Ashby charts

All tools operate on the full material database (base + extended, ≥ 200 materials).
They are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.matsel.multi_objective import (
    pareto_frontier,
    weighted_score,
    tradeoff_envelope,
)


# ---------------------------------------------------------------------------
# Tool: matsel_pareto
# ---------------------------------------------------------------------------

_pareto_spec = ToolSpec(
    name="matsel_pareto",
    description=(
        "Find the Pareto-optimal (non-dominated) set of materials for multiple "
        "simultaneous objectives.\n"
        "\n"
        "A material is non-dominated if no other material is at least as good "
        "on every objective and strictly better on at least one.  This is the "
        "Granta/CES Selector 'Pareto front' for material trade-off analysis.\n"
        "\n"
        "Operates on the full material database (base + extended, ≥ 200 materials).\n"
        "\n"
        "Available properties / objectives:\n"
        "  Base: density (kg/m³), E (GPa), sigma_y (MPa), sigma_uts (MPa),\n"
        "        sigma_e (MPa), k (W/m·K), CTE (µm/m·K), T_max (°C), cost_rel\n"
        "  Ashby indices: specific_stiffness (E/ρ), specific_strength (σy/ρ),\n"
        "        light_stiff_beam (E^0.5/ρ), light_strong_plate (σy^(2/3)/ρ),\n"
        "        cost_per_stiffness (cost·ρ/E)\n"
        "  Extended: co2_kg_kg (kg CO₂-eq/kg), specific_heat (J/kg·K)\n"
        "\n"
        "Returns the non-dominated set with per-objective values.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid input.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "objectives": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "List of property / merit-index names to optimise, "
                    "e.g. ['density', 'E'] or ['specific_stiffness', 'cost_rel']."
                ),
            },
            "directions": {
                "type": "array",
                "items": {"type": "string", "enum": ["min", "max"]},
                "description": (
                    "'min' or 'max' for each objective.  Must have same length as "
                    "objectives.  E.g. ['min', 'max'] means minimise first objective "
                    "and maximise second."
                ),
            },
        },
        "required": ["objectives", "directions"],
    },
)


@register(_pareto_spec, write=False)
async def run_matsel_pareto(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    objectives = a.get("objectives")
    directions = a.get("directions")

    if not isinstance(objectives, list) or not objectives:
        return json.dumps({"ok": False, "reason": "objectives must be a non-empty list"})
    if not isinstance(directions, list) or not directions:
        return json.dumps({"ok": False, "reason": "directions must be a non-empty list"})

    result = pareto_frontier(objectives=objectives, directions=directions)
    if not result["ok"]:
        return json.dumps(result)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: matsel_weighted
# ---------------------------------------------------------------------------

_weighted_spec = ToolSpec(
    name="matsel_weighted",
    description=(
        "Rank materials by a linear weighted sum of multiple objectives.\n"
        "\n"
        "Each objective is min-max normalised to [0,1] (when normalise=true) "
        "so objectives with different units can be compared.  A 'min' direction "
        "is flipped so that a higher weighted score is always better.\n"
        "\n"
        "A single non-zero weight with normalise=true reproduces the existing "
        "single-objective Ashby ranking.\n"
        "\n"
        "Operates on the full material database (base + extended, ≥ 200 materials).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid input.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "objectives": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Property / merit-index names to include in ranking.",
            },
            "weights": {
                "type": "array",
                "items": {"type": "number"},
                "description": (
                    "Non-negative weight for each objective (same length as objectives). "
                    "Need not sum to 1."
                ),
            },
            "directions": {
                "type": "array",
                "items": {"type": "string", "enum": ["min", "max"]},
                "description": (
                    "'min' or 'max' per objective.  If omitted, defaults are inferred "
                    "(density/cost/CTE → min; all others → max)."
                ),
            },
            "normalise": {
                "type": "boolean",
                "description": "Min-max normalise objectives before weighting (default true).",
            },
            "top_n": {
                "type": "integer",
                "description": "Maximum number of results to return (default all).",
            },
        },
        "required": ["objectives", "weights"],
    },
)


@register(_weighted_spec, write=False)
async def run_matsel_weighted(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    objectives = a.get("objectives")
    weights = a.get("weights")
    directions = a.get("directions")
    normalise = a.get("normalise", True)
    top_n = a.get("top_n")

    if not isinstance(objectives, list) or not objectives:
        return json.dumps({"ok": False, "reason": "objectives must be a non-empty list"})
    if not isinstance(weights, list) or not weights:
        return json.dumps({"ok": False, "reason": "weights must be a non-empty list"})

    result = weighted_score(
        objectives=objectives,
        weights=weights,
        directions=directions,
        normalise=bool(normalise),
        top_n=top_n,
    )
    if not result["ok"]:
        return json.dumps(result)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: matsel_tradeoff
# ---------------------------------------------------------------------------

_tradeoff_spec = ToolSpec(
    name="matsel_tradeoff",
    description=(
        "Compute the convex Pareto envelope for a two-objective Ashby chart.\n"
        "\n"
        "Returns the subset of materials lying on the convex upper-right boundary "
        "(for two 'max' objectives) or appropriate corner for mixed directions.  "
        "These are the materials that define the performance envelope — no linear "
        "combination of the two objectives can be improved without moving off the "
        "envelope.\n"
        "\n"
        "Operates on the full material database (base + extended, ≥ 200 materials).\n"
        "\n"
        "Also returns all_points for scatter-chart plotting.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid input.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "x_metric": {
                "type": "string",
                "description": "Property / merit-index for the chart x-axis.",
            },
            "y_metric": {
                "type": "string",
                "description": "Property / merit-index for the chart y-axis.",
            },
            "x_direction": {
                "type": "string",
                "enum": ["min", "max"],
                "description": "Optimisation direction for x-axis (default 'max').",
            },
            "y_direction": {
                "type": "string",
                "enum": ["min", "max"],
                "description": "Optimisation direction for y-axis (default 'max').",
            },
        },
        "required": ["x_metric", "y_metric"],
    },
)


@register(_tradeoff_spec, write=False)
async def run_matsel_tradeoff(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    x_metric = a.get("x_metric")
    y_metric = a.get("y_metric")
    if not x_metric or not y_metric:
        return json.dumps({"ok": False, "reason": "x_metric and y_metric are required"})

    x_direction = a.get("x_direction", "max")
    y_direction = a.get("y_direction", "max")

    result = tradeoff_envelope(
        x_metric=x_metric,
        y_metric=y_metric,
        x_direction=x_direction,
        y_direction=y_direction,
    )
    if not result["ok"]:
        return json.dumps(result)
    return ok_payload(result)
