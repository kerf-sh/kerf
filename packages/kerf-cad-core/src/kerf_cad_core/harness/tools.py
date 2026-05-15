"""
kerf_cad_core.harness.tools — LLM tool wrappers for 3D wiring harness routing.

Registers three tools with the Kerf tool registry:

  harness_route          — Route a harness in 3D; returns path, length, OD,
                           bend-radius check, and branch model.
  harness_bundle_diameter — Compute bundle OD from wire count + gauge.
  harness_bom            — Roll up wire lengths per segment/branch into a BOM.

All tools are pure-Python; no OCC dependency.  Inputs are validated and
errors returned as {ok: false, reason: "..."} — tools never raise.

Units: metres (m).  Wire gauges: mm² cross-section area strings.

Author: imranparuk
"""
from __future__ import annotations

import json
from typing import Any

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.harness.route import (
    WireSpec,
    bundle_diameter,
    harness_bom,
    route_harness,
)


# ---------------------------------------------------------------------------
# Tool: harness_route
# ---------------------------------------------------------------------------

_route_spec = ToolSpec(
    name="harness_route",
    description=(
        "Route a wiring harness in 3D through connector endpoints and optional "
        "guide (via) points, producing a smoothed polyline bundle path.\n"
        "\n"
        "Inputs:\n"
        "  endpoints   — list of exactly 2 (or more for trunk) {x,y,z} points\n"
        "  guides      — optional list of via-points the harness passes near\n"
        "  wire_specs  — optional [{gauge, count}, ...] wire specifications\n"
        "                gauge is mm² cross-section string e.g. '1.0', '2.5'\n"
        "  obstacles   — optional list of {min_x,min_y,min_z,max_x,max_y,max_z}\n"
        "                obstacle bounding boxes (metres)\n"
        "  branches    — optional list of T-split branches:\n"
        "                [{branch_id, start, end, guides, wire_specs}, ...]\n"
        "\n"
        "Smoothing: centripetal Catmull-Rom spline (alpha=0.5) through "
        "control points.\n"
        "\n"
        "Output: {ok, reason, total_length_m, bundle_od_mm, obstacles_hit, "
        "branch_count, branches: [{branch_id, total_length_m, bend_ok, "
        "segments: [{name, length_m, bundle_od_mm, min_bend_radius_m, "
        "bend_ok, wire_count, control_points, smoothed_point_count}]}]}.\n"
        "\n"
        "ok=false when bend-radius check fails (min bend radius < 10× bundle "
        "OD) or path intersects an obstacle — the violation is reported in "
        "'reason', never raised as an exception.\n"
        "\n"
        "Units: metres.  All coordinates in metres."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "endpoints": {
                "type": "array",
                "description": (
                    "Connector endpoints as [{x,y,z}, ...] (metres). "
                    "Minimum 2 points: [start, end]."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "number"},
                        "y": {"type": "number"},
                        "z": {"type": "number"},
                    },
                    "required": ["x", "y", "z"],
                },
                "minItems": 2,
            },
            "guides": {
                "type": "array",
                "description": (
                    "Optional via-points for trunk routing ({x,y,z} metres). "
                    "The harness is smoothed through these points."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "number"},
                        "y": {"type": "number"},
                        "z": {"type": "number"},
                    },
                    "required": ["x", "y", "z"],
                },
            },
            "wire_specs": {
                "type": "array",
                "description": (
                    "Wire specifications [{gauge, count}]. "
                    "gauge: mm² cross-section area string e.g. '0.5', '1.0', '2.5'. "
                    "count: number of wires of that gauge."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "gauge": {"type": "string"},
                        "count": {"type": "integer", "minimum": 1},
                    },
                    "required": ["gauge", "count"],
                },
            },
            "obstacles": {
                "type": "array",
                "description": (
                    "Axis-aligned obstacle bounding boxes "
                    "{min_x, min_y, min_z, max_x, max_y, max_z} (metres). "
                    "Path flagged if any point lies inside a bbox."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "min_x": {"type": "number"},
                        "min_y": {"type": "number"},
                        "min_z": {"type": "number"},
                        "max_x": {"type": "number"},
                        "max_y": {"type": "number"},
                        "max_z": {"type": "number"},
                    },
                    "required": ["min_x", "min_y", "min_z", "max_x", "max_y", "max_z"],
                },
            },
            "branches": {
                "type": "array",
                "description": (
                    "T-split branch definitions. Each branch: "
                    "{branch_id, start?, end (required), guides?, wire_specs?}. "
                    "If start is omitted, branch starts from endpoints[1] (trunk end)."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "branch_id": {"type": "string"},
                        "start": {
                            "type": "object",
                            "properties": {
                                "x": {"type": "number"},
                                "y": {"type": "number"},
                                "z": {"type": "number"},
                            },
                        },
                        "end": {
                            "type": "object",
                            "properties": {
                                "x": {"type": "number"},
                                "y": {"type": "number"},
                                "z": {"type": "number"},
                            },
                            "required": ["x", "y", "z"],
                        },
                        "guides": {"type": "array"},
                        "wire_specs": {"type": "array"},
                    },
                    "required": ["end"],
                },
            },
        },
        "required": ["endpoints"],
    },
)


@register(_route_spec, write=False)
async def run_harness_route(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    endpoints_raw = a.get("endpoints")
    if not isinstance(endpoints_raw, list):
        return json.dumps({"ok": False, "reason": "endpoints must be a list"})

    guides_raw = a.get("guides") or []
    wire_specs_raw = a.get("wire_specs") or []
    obstacles_raw = a.get("obstacles") or []
    branches_raw = a.get("branches") or []

    # Parse wire_specs
    wire_specs: list[WireSpec] = []
    for ws in wire_specs_raw:
        try:
            wire_specs.append(WireSpec(gauge=str(ws["gauge"]), count=int(ws["count"])))
        except (KeyError, TypeError, ValueError) as exc:
            return json.dumps({"ok": False, "reason": f"invalid wire_spec: {exc}"})

    result = route_harness(
        endpoints=endpoints_raw,
        guides=guides_raw,
        wire_specs=wire_specs,
        obstacles=obstacles_raw,
        branches=branches_raw,
    )

    return ok_payload(result.to_dict())


# ---------------------------------------------------------------------------
# Tool: harness_bundle_diameter
# ---------------------------------------------------------------------------

_bundle_diam_spec = ToolSpec(
    name="harness_bundle_diameter",
    description=(
        "Compute the outer diameter of a wiring harness bundle from wire "
        "count and gauge specifications.\n"
        "\n"
        "Method: sum all insulated wire cross-section areas, divide by bundle "
        "fill factor (0.78, hexagonal close-packing approximation), compute "
        "equivalent circular bundle diameter.\n"
        "\n"
        "Input: [{gauge, count}, ...] wire specifications.\n"
        "  gauge: mm² cross-section area string e.g. '0.5', '1.0', '2.5'\n"
        "  count: number of wires of that gauge\n"
        "\n"
        "Output: {ok, bundle_od_mm, bundle_od_m, wire_count_total, "
        "wire_specs_parsed}.\n"
        "\n"
        "Errors returned as {ok: false, reason: ...}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "wire_specs": {
                "type": "array",
                "description": (
                    "Wire specifications [{gauge, count}]. "
                    "gauge: mm² cross-section area string. "
                    "count: number of wires of that gauge."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "gauge": {"type": "string"},
                        "count": {"type": "integer", "minimum": 1},
                    },
                    "required": ["gauge", "count"],
                },
                "minItems": 1,
            },
        },
        "required": ["wire_specs"],
    },
)


@register(_bundle_diam_spec, write=False)
async def run_harness_bundle_diameter(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    wire_specs_raw = a.get("wire_specs")
    if not isinstance(wire_specs_raw, list) or len(wire_specs_raw) == 0:
        return json.dumps({"ok": False, "reason": "wire_specs must be a non-empty list"})

    wire_specs: list[WireSpec] = []
    for ws in wire_specs_raw:
        try:
            wire_specs.append(WireSpec(gauge=str(ws["gauge"]), count=int(ws["count"])))
        except (KeyError, TypeError, ValueError) as exc:
            return json.dumps({"ok": False, "reason": f"invalid wire_spec: {exc}"})

    od_m = bundle_diameter(wire_specs)
    total_count = sum(ws.count for ws in wire_specs)

    return ok_payload({
        "ok": True,
        "bundle_od_mm": round(od_m * 1000, 3),
        "bundle_od_m": round(od_m, 6),
        "wire_count_total": total_count,
        "wire_specs_parsed": [{"gauge": ws.gauge, "count": ws.count} for ws in wire_specs],
    })


# ---------------------------------------------------------------------------
# Tool: harness_bom
# ---------------------------------------------------------------------------

_bom_spec = ToolSpec(
    name="harness_bom",
    description=(
        "Generate a wire/length/segment rollup Bill of Materials (BOM) from "
        "a routed harness result.\n"
        "\n"
        "Input: a harness result dict from harness_route (the full JSON output).\n"
        "\n"
        "For each segment in each branch, the BOM lists:\n"
        "  gauge         — wire gauge (mm² cross-section)\n"
        "  count         — number of wires of that gauge in the segment\n"
        "  segment_name  — segment identifier\n"
        "  branch_id     — branch identifier\n"
        "  length_m      — routed length of the segment\n"
        "  total_wire_length_m — count × length_m (material to procure)\n"
        "\n"
        "Output: {ok, entries: [...], totals_by_gauge: {gauge: total_m}, "
        "grand_total_wire_length_m}.\n"
        "\n"
        "totals_by_gauge sums total_wire_length_m across all segments for "
        "each gauge — use this for procurement quantities.\n"
        "\n"
        "Errors returned as {ok: false, reason: ...}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "harness": {
                "type": "object",
                "description": (
                    "Harness result dict from harness_route. "
                    "Must contain 'branches' list with segments."
                ),
            },
            "wire_specs": {
                "type": "array",
                "description": (
                    "Optional wire_specs to assign to segments that have none. "
                    "If the harness was routed without wire_specs, provide them here."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "gauge": {"type": "string"},
                        "count": {"type": "integer", "minimum": 1},
                    },
                    "required": ["gauge", "count"],
                },
            },
        },
        "required": ["harness"],
    },
)


@register(_bom_spec, write=False)
async def run_harness_bom(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    harness_dict = a.get("harness")
    if not isinstance(harness_dict, dict):
        return json.dumps({"ok": False, "reason": "harness must be the output dict from harness_route"})

    branches_raw = harness_dict.get("branches")
    if not isinstance(branches_raw, list):
        return json.dumps({"ok": False, "reason": "harness.branches must be a list"})

    # Optional fallback wire_specs
    fallback_specs_raw = a.get("wire_specs") or []
    fallback_specs: list[WireSpec] = []
    for ws in fallback_specs_raw:
        try:
            fallback_specs.append(WireSpec(gauge=str(ws["gauge"]), count=int(ws["count"])))
        except (KeyError, TypeError, ValueError):
            pass

    # Build BOM entries from raw dict
    entries: list[dict] = []
    totals: dict[str, float] = {}

    for branch in branches_raw:
        b_id = str(branch.get("branch_id", "unknown"))
        for seg in branch.get("segments", []):
            seg_name = str(seg.get("name", "segment"))
            seg_length = float(seg.get("length_m", 0.0))

            # Reconstruct wire_specs from seg if present; otherwise use fallback
            seg_specs_raw = seg.get("wire_specs")
            if seg_specs_raw:
                seg_specs = [
                    WireSpec(gauge=str(ws["gauge"]), count=int(ws["count"]))
                    for ws in seg_specs_raw
                    if isinstance(ws, dict)
                ]
            else:
                seg_specs = fallback_specs

            for ws in seg_specs:
                total_wl = seg_length * ws.count
                entry = {
                    "gauge": ws.gauge,
                    "count": ws.count,
                    "segment_name": seg_name,
                    "branch_id": b_id,
                    "length_m": round(seg_length, 6),
                    "total_wire_length_m": round(total_wl, 6),
                }
                entries.append(entry)
                totals[ws.gauge] = totals.get(ws.gauge, 0.0) + total_wl

    grand_total = sum(totals.values())

    return ok_payload({
        "ok": True,
        "entries": entries,
        "totals_by_gauge": {g: round(v, 6) for g, v in totals.items()},
        "grand_total_wire_length_m": round(grand_total, 6),
    })
