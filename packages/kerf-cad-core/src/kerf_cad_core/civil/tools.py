"""
kerf_cad_core.civil.tools — LLM tool wrappers for site grading & earthwork.

Registers four tools with the Kerf tool registry:

  civil_terrain        — Build a TIN from survey points; return area, elevation
                         stats and triangle count.
  civil_pad            — Define a flat or sloped design platform (polygon +
                         elevation + optional side slopes).
  civil_earthwork      — Compute cut/fill volumes (m³) between an existing TIN
                         and a design surface; return balance report.
  civil_grading_report — Format a human-readable grading summary from earthwork
                         results.

All tools are pure-Python; no OCC dependency.  Inputs are validated and
errors returned as {ok: false, errors: [...]} — tools never raise.

Units: metres (m), metres³ (m³).
Author: imranparuk
"""
from __future__ import annotations

import json
import math
from typing import Any

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.civil.terrain import build_tin, Point3D, TIN
from kerf_cad_core.civil.earthwork import (
    DesignSurface,
    compute_earthwork,
    validate_polygon,
    EarthworkResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_points(raw: Any) -> tuple[list[dict] | None, str | None]:
    """Return (list_of_point_dicts, error_string_or_None)."""
    if not isinstance(raw, list):
        return None, "points must be a list of {x,y,z} objects"
    return raw, None


def _ok_or_err(errors: list[str]) -> str | None:
    """Return JSON error payload if errors list is non-empty, else None."""
    if errors:
        return json.dumps({"ok": False, "errors": errors})
    return None


# ---------------------------------------------------------------------------
# Tool: civil_terrain
# ---------------------------------------------------------------------------

_terrain_spec = ToolSpec(
    name="civil_terrain",
    description=(
        "Build a Triangulated Irregular Network (TIN) from survey points and "
        "return surface statistics.\n"
        "\n"
        "Input: a list of {x, y, z} objects (metres) — at least 3 non-collinear "
        "points.\n"
        "\n"
        "Output: {ok, point_count, triangle_count, area_m2, min_elevation_m, "
        "max_elevation_m, elevation_range_m}.\n"
        "\n"
        "Errors returned as {ok: false, errors: [...]} for < 3 points or "
        "collinear inputs.  Never raises.\n"
        "\n"
        "Triangulation: fan method (hub = lexicographically first point; "
        "remaining points sorted by polar angle).  Deterministic and consistent "
        "for any input order.\n"
        "\n"
        "Use this tool first before civil_earthwork.  The tin_points list is "
        "passed verbatim to civil_earthwork."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "points": {
                "type": "array",
                "description": (
                    "Survey points as {x, y, z} objects (metres). "
                    "Minimum 3 non-collinear points required."
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
        },
        "required": ["points"],
    },
)


@register(_terrain_spec, write=False)
async def run_civil_terrain(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    raw_points, perr = _parse_points(a.get("points"))
    if perr:
        return json.dumps({"ok": False, "errors": [perr]})

    tin, errors = build_tin(raw_points)
    if errors:
        return json.dumps({"ok": False, "errors": errors})

    summary = tin.summary()
    summary["ok"] = True
    return ok_payload(summary)


# ---------------------------------------------------------------------------
# Tool: civil_pad
# ---------------------------------------------------------------------------

_pad_spec = ToolSpec(
    name="civil_pad",
    description=(
        "Define a flat or sloped design platform (pad) for earthwork planning.\n"
        "\n"
        "A pad is a proposed graded surface defined by:\n"
        "  - A polygon boundary (list of [x, y] pairs, ≥ 3 vertices)\n"
        "  - A pad elevation at the polygon centroid (metres)\n"
        "  - An optional side-slope ratio (1V:nH — horizontal run per 1 m "
        "    vertical; e.g. 2.0 means the pad slopes 1 m vertically per 2 m "
        "    horizontally from the edge)\n"
        "  - Optional tilt (dz_dx, dz_dy) to define a sloped pad instead of flat\n"
        "\n"
        "Output: {ok, pad_elevation, polygon_vertex_count, side_slope_ratio, "
        "sloped, dz_dx, dz_dy, design_surface_json}.\n"
        "\n"
        "The design_surface_json field can be passed directly to civil_earthwork "
        "as the design_surface parameter.\n"
        "\n"
        "Errors returned as {ok: false, errors: [...]} for invalid inputs."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "polygon": {
                "type": "array",
                "description": (
                    "Pad boundary as a list of [x, y] pairs (metres). "
                    "At least 3 vertices required. "
                    "Example: [[0,0],[10,0],[10,10],[0,10]]"
                ),
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 2,
                },
            },
            "pad_elevation": {
                "type": "number",
                "description": "Target elevation of the flat pad surface (metres).",
            },
            "side_slope_ratio": {
                "type": "number",
                "description": (
                    "Horizontal run per 1 m of vertical rise (1V:nH). "
                    "E.g. 2.0 for a 2H:1V slope. "
                    "Set to 0 (default) for no side slopes (pad edges are vertical)."
                ),
            },
            "sloped": {
                "type": "boolean",
                "description": (
                    "If true, the pad surface is a tilted plane; "
                    "pad_elevation applies at the polygon centroid and "
                    "dz_dx / dz_dy define the tilt. Default false."
                ),
            },
            "dz_dx": {
                "type": "number",
                "description": "Elevation gradient in X direction (m/m). Used when sloped=true.",
            },
            "dz_dy": {
                "type": "number",
                "description": "Elevation gradient in Y direction (m/m). Used when sloped=true.",
            },
        },
        "required": ["polygon", "pad_elevation"],
    },
)


@register(_pad_spec, write=False)
async def run_civil_pad(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    polygon_raw = a.get("polygon")
    pad_elevation = a.get("pad_elevation")
    side_slope_ratio = float(a.get("side_slope_ratio", 0.0))
    sloped = bool(a.get("sloped", False))
    dz_dx = float(a.get("dz_dx", 0.0))
    dz_dy = float(a.get("dz_dy", 0.0))

    if pad_elevation is None:
        return json.dumps({"ok": False, "errors": ["pad_elevation is required"]})

    try:
        pad_elevation = float(pad_elevation)
    except (TypeError, ValueError):
        return json.dumps({"ok": False, "errors": ["pad_elevation must be a number"]})

    poly_errors = validate_polygon(polygon_raw)
    if poly_errors:
        return json.dumps({"ok": False, "errors": poly_errors})

    ring = [(float(pt[0]), float(pt[1])) for pt in polygon_raw]

    design = DesignSurface(
        pad_elevation=pad_elevation,
        polygon=ring,
        side_slope_ratio=side_slope_ratio,
        sloped=sloped,
        dz_dx=dz_dx,
        dz_dy=dz_dy,
    )
    ds_errors = design.validate()
    if ds_errors:
        return json.dumps({"ok": False, "errors": ds_errors})

    # Serialise DesignSurface config so it can be forwarded to civil_earthwork.
    ds_json = {
        "pad_elevation": pad_elevation,
        "polygon": ring,
        "side_slope_ratio": side_slope_ratio,
        "sloped": sloped,
        "dz_dx": dz_dx,
        "dz_dy": dz_dy,
    }

    return ok_payload({
        "ok": True,
        "pad_elevation": pad_elevation,
        "polygon_vertex_count": len(ring),
        "side_slope_ratio": side_slope_ratio,
        "sloped": sloped,
        "dz_dx": dz_dx,
        "dz_dy": dz_dy,
        "design_surface_json": ds_json,
        "note": (
            "Pass design_surface_json to civil_earthwork as the "
            "'design_surface' parameter."
        ),
    })


# ---------------------------------------------------------------------------
# Tool: civil_earthwork
# ---------------------------------------------------------------------------

_earthwork_spec = ToolSpec(
    name="civil_earthwork",
    description=(
        "Compute cut/fill earthwork volumes between an existing ground surface "
        "(TIN) and a proposed design surface (pad).\n"
        "\n"
        "Method: grid sampling at a configurable spacing (default 1 m). "
        "At each sample node the existing elevation is interpolated from the TIN "
        "and compared with the design surface elevation:\n"
        "  Δz > 0 → fill (add material)\n"
        "  Δz < 0 → cut  (remove material)\n"
        "Volume = |Δz| × cell_area (m³).\n"
        "\n"
        "Output: {ok, cut_m3, fill_m3, net_m3, balance_ratio, sample_count, "
        "grid_spacing_m, cell_area_m2, note}.\n"
        "\n"
        "balance_ratio = cut / fill. Value ≈ 1.0 → balanced earthwork. "
        "> 1 → surplus cut; < 1 → import fill required.\n"
        "\n"
        "Errors returned as {ok: false, errors: [...]}. Never raises.\n"
        "\n"
        "Typical workflow:\n"
        "  1. civil_terrain(points=...) → collect survey points\n"
        "  2. civil_pad(polygon=..., pad_elevation=...) → design_surface_json\n"
        "  3. civil_earthwork(tin_points=..., design_surface=design_surface_json)"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "tin_points": {
                "type": "array",
                "description": (
                    "Existing ground survey points as {x, y, z} objects (metres). "
                    "Same list passed to civil_terrain."
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
            "design_surface": {
                "type": "object",
                "description": (
                    "Design surface specification from civil_pad output "
                    "(design_surface_json field). "
                    "Fields: pad_elevation, polygon, side_slope_ratio, "
                    "sloped, dz_dx, dz_dy."
                ),
            },
            "grid_spacing_m": {
                "type": "number",
                "description": (
                    "Sample grid spacing in metres (default 1.0). "
                    "Smaller values give more accurate volumes at higher cost. "
                    "Typical range: 0.5–5.0 m."
                ),
            },
        },
        "required": ["tin_points", "design_surface"],
    },
)


@register(_earthwork_spec, write=False)
async def run_civil_earthwork(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    tin_points_raw = a.get("tin_points")
    design_raw = a.get("design_surface")
    grid_spacing = float(a.get("grid_spacing_m", 1.0))

    # Validate grid spacing
    if grid_spacing <= 0:
        return json.dumps({"ok": False, "errors": [
            f"grid_spacing_m must be > 0; got {grid_spacing}"
        ]})

    # Build TIN
    raw_pts, perr = _parse_points(tin_points_raw)
    if perr:
        return json.dumps({"ok": False, "errors": [perr]})

    tin, tin_errors = build_tin(raw_pts)
    if tin_errors:
        return json.dumps({"ok": False, "errors": tin_errors})

    # Build DesignSurface
    if not isinstance(design_raw, dict):
        return json.dumps({"ok": False, "errors": [
            "design_surface must be an object (use civil_pad output)"
        ]})

    polygon_raw = design_raw.get("polygon")
    poly_errors = validate_polygon(polygon_raw)
    if poly_errors:
        return json.dumps({"ok": False, "errors": poly_errors})

    pad_elevation_raw = design_raw.get("pad_elevation")
    if pad_elevation_raw is None:
        return json.dumps({"ok": False, "errors": [
            "design_surface.pad_elevation is required"
        ]})

    try:
        pad_elevation = float(pad_elevation_raw)
    except (TypeError, ValueError):
        return json.dumps({"ok": False, "errors": [
            "design_surface.pad_elevation must be a number"
        ]})

    ring = [(float(pt[0]), float(pt[1])) for pt in polygon_raw]
    design = DesignSurface(
        pad_elevation=pad_elevation,
        polygon=ring,
        side_slope_ratio=float(design_raw.get("side_slope_ratio", 0.0)),
        sloped=bool(design_raw.get("sloped", False)),
        dz_dx=float(design_raw.get("dz_dx", 0.0)),
        dz_dy=float(design_raw.get("dz_dy", 0.0)),
    )
    ds_errors = design.validate()
    if ds_errors:
        return json.dumps({"ok": False, "errors": ds_errors})

    # Run computation
    try:
        result = compute_earthwork(tin, design, grid_spacing=grid_spacing)
    except Exception as exc:
        return json.dumps({"ok": False, "errors": [f"computation error: {exc}"]})

    payload = result.to_dict()
    payload["ok"] = True
    return ok_payload(payload)


# ---------------------------------------------------------------------------
# Tool: civil_grading_report
# ---------------------------------------------------------------------------

_grading_report_spec = ToolSpec(
    name="civil_grading_report",
    description=(
        "Format a human-readable grading & earthwork balance report from "
        "civil_earthwork output.\n"
        "\n"
        "Input: the output dict from civil_earthwork (ok, cut_m3, fill_m3, "
        "net_m3, balance_ratio, etc.).\n"
        "\n"
        "Output: {ok, report_text, summary_lines} where report_text is a "
        "formatted multi-line string suitable for display or saving, and "
        "summary_lines is the same content as a list of strings.\n"
        "\n"
        "Also accepts optional project_name and site_description strings for "
        "the report header."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "earthwork": {
                "type": "object",
                "description": (
                    "Earthwork result dict from civil_earthwork. "
                    "Required fields: cut_m3, fill_m3, net_m3, balance_ratio, "
                    "sample_count, grid_spacing_m."
                ),
            },
            "project_name": {
                "type": "string",
                "description": "Optional project name for the report header.",
            },
            "site_description": {
                "type": "string",
                "description": "Optional site description or notes.",
            },
        },
        "required": ["earthwork"],
    },
)


@register(_grading_report_spec, write=False)
async def run_civil_grading_report(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    ew = a.get("earthwork")
    if not isinstance(ew, dict):
        return json.dumps({"ok": False, "errors": [
            "earthwork must be the output dict from civil_earthwork"
        ]})

    project_name = str(a.get("project_name", "Untitled Project"))
    site_desc = str(a.get("site_description", ""))

    try:
        cut = float(ew.get("cut_m3", 0))
        fill = float(ew.get("fill_m3", 0))
        net = float(ew.get("net_m3", 0))
        ratio_raw = ew.get("balance_ratio")
        ratio = float(ratio_raw) if ratio_raw is not None else math.inf
        samples = int(ew.get("sample_count", 0))
        spacing = float(ew.get("grid_spacing_m", 1.0))
    except (TypeError, ValueError) as exc:
        return json.dumps({"ok": False, "errors": [
            f"earthwork field parse error: {exc}"
        ]})

    note = ew.get("note", "")

    lines: list[str] = [
        "=" * 56,
        "  EARTHWORK & GRADING REPORT",
        f"  Project : {project_name}",
    ]
    if site_desc:
        lines.append(f"  Site    : {site_desc}")
    lines += [
        "=" * 56,
        f"  Cut volume  : {cut:>12.2f} m³",
        f"  Fill volume : {fill:>12.2f} m³",
        f"  Net volume  : {net:>12.2f} m³"
        + (" (import fill)" if net > 0 else " (export cut)" if net < 0 else ""),
        f"  Balance     : {ratio:.3f}" + (" (cut/fill ratio)" if math.isfinite(ratio) else " (∞ — all cut)"),
        "-" * 56,
        f"  Sample grid : {spacing} m spacing",
        f"  Sample count: {samples}",
        f"  Balance note: {note}",
        "=" * 56,
    ]

    report_text = "\n".join(lines)

    return ok_payload({
        "ok": True,
        "report_text": report_text,
        "summary_lines": lines,
    })
