"""
kerf_cad_core.scan.tools — LLM tool wrappers for scan-to-CAD point-cloud fitting.

Registers five tools:

  scan_load           — Ingest a point list; return count, bbox, centroid.
  scan_fit_plane      — RANSAC plane fit; returns normal, d, inlier_ratio, residual.
  scan_fit_sphere     — RANSAC sphere fit; returns centre, radius, inlier_ratio, residual.
  scan_fit_cylinder   — RANSAC cylinder fit; returns axis, axis_point, radius, inlier_ratio.
  scan_segment        — Greedy multi-primitive segmentation of a mixed cloud.

All tools are pure-Python; no OCC dependency.
Errors returned as {ok: false, reason: "..."} — tools never raise.

Author: imranparuk
"""
from __future__ import annotations

import json
from typing import Any

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.scan.fit import (
    cloud_stats,
    ransac_fit_plane,
    ransac_fit_sphere,
    ransac_fit_cylinder,
    greedy_segment,
)

# ---------------------------------------------------------------------------
# Shared point-list schema fragment
# ---------------------------------------------------------------------------

_POINT_ITEMS = {
    "type": "array",
    "items": {"type": "number"},
    "minItems": 3,
    "maxItems": 3,
    "description": "A single point as [x, y, z].",
}

_POINTS_PROP = {
    "type": "array",
    "description": "List of 3-D points as [[x,y,z], ...]. Minimum 3 points.",
    "items": _POINT_ITEMS,
}


# ---------------------------------------------------------------------------
# Helper: parse & validate raw points arg
# ---------------------------------------------------------------------------

def _parse_points(raw: Any) -> tuple[list[list[float]] | None, str | None]:
    """Validate and coerce raw points to list[list[float]].

    Returns (pts, None) on success or (None, reason_str) on error.
    """
    if not isinstance(raw, list):
        return None, "points must be a list of [x, y, z] arrays"
    pts: list[list[float]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            return None, f"point[{i}] must be an array of exactly 3 numbers"
        try:
            pts.append([float(item[0]), float(item[1]), float(item[2])])
        except (TypeError, ValueError):
            return None, f"point[{i}] contains non-numeric value"
    return pts, None


# ---------------------------------------------------------------------------
# Tool: scan_load
# ---------------------------------------------------------------------------

_scan_load_spec = ToolSpec(
    name="scan_load",
    description=(
        "Ingest a raw point cloud and return summary statistics.\n"
        "\n"
        "Accepts a list of [x, y, z] triples (any units — millimetres, metres, "
        "inches, etc.) and returns count, axis-aligned bounding box, and centroid.\n"
        "\n"
        "Output: {ok, count, bbox: {x_min,x_max,y_min,y_max,z_min,z_max}, centroid: [x,y,z]}.\n"
        "\n"
        "Use this as the first step before calling scan_fit_* or scan_segment.\n"
        "\n"
        "Errors: {ok:false, reason} for empty or malformed input. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "points": _POINTS_PROP,
        },
        "required": ["points"],
    },
)


@register(_scan_load_spec, write=False)
async def run_scan_load(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    pts, err = _parse_points(a.get("points"))
    if err:
        return json.dumps({"ok": False, "reason": err})

    result = cloud_stats(pts)
    if not result["ok"]:
        return json.dumps(result)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: scan_fit_plane
# ---------------------------------------------------------------------------

_scan_fit_plane_spec = ToolSpec(
    name="scan_fit_plane",
    description=(
        "Fit a plane to a point cloud using RANSAC + least-squares (PCA normal).\n"
        "\n"
        "The algorithm:\n"
        "  1. Randomly sample 3 points, fit a plane via PCA on centred cloud.\n"
        "  2. Count inliers within `threshold` distance of the plane.\n"
        "  3. Repeat for `n_iters` iterations; refit on the best inlier set.\n"
        "\n"
        "RANSAC is deterministic: same points + same seed → same result.\n"
        "\n"
        "Output: {ok, primitive:'plane', normal:[nx,ny,nz], d, centre:[x,y,z], "
        "inlier_ratio, residual}.\n"
        "Plane equation: normal · p = d.\n"
        "\n"
        "Errors: {ok:false, reason} for <3 points, collinear input, or no "
        "consensus set. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "points": _POINTS_PROP,
            "threshold": {
                "type": "number",
                "description": (
                    "Maximum point-to-plane distance to count as an inlier "
                    "(same units as points). Default 0.01."
                ),
            },
            "n_iters": {
                "type": "integer",
                "description": "Number of RANSAC iterations. Default 200.",
            },
            "seed": {
                "type": "integer",
                "description": "Random seed for reproducibility. Default 42.",
            },
        },
        "required": ["points"],
    },
)


@register(_scan_fit_plane_spec, write=False)
async def run_scan_fit_plane(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    pts, err = _parse_points(a.get("points"))
    if err:
        return json.dumps({"ok": False, "reason": err})

    threshold = float(a.get("threshold", 0.01))
    n_iters = int(a.get("n_iters", 200))
    seed = int(a.get("seed", 42))

    result = ransac_fit_plane(pts, threshold=threshold, n_iters=n_iters, seed=seed)
    if not result["ok"]:
        return json.dumps(result)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: scan_fit_sphere
# ---------------------------------------------------------------------------

_scan_fit_sphere_spec = ToolSpec(
    name="scan_fit_sphere",
    description=(
        "Fit a sphere to a point cloud using RANSAC + algebraic least squares.\n"
        "\n"
        "Minimum 4 points required (the algebraic minimum for a unique sphere).\n"
        "\n"
        "Output: {ok, primitive:'sphere', centre:[x,y,z], radius, "
        "inlier_ratio, residual}.\n"
        "\n"
        "RANSAC is deterministic: same points + same seed → same result.\n"
        "\n"
        "Errors: {ok:false, reason} for <4 points, degenerate geometry, or no "
        "consensus. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "points": _POINTS_PROP,
            "threshold": {
                "type": "number",
                "description": (
                    "Maximum point-to-sphere-surface distance to count as an "
                    "inlier (same units as points). Default 0.01."
                ),
            },
            "n_iters": {
                "type": "integer",
                "description": "Number of RANSAC iterations. Default 200.",
            },
            "seed": {
                "type": "integer",
                "description": "Random seed for reproducibility. Default 42.",
            },
        },
        "required": ["points"],
    },
)


@register(_scan_fit_sphere_spec, write=False)
async def run_scan_fit_sphere(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    pts, err = _parse_points(a.get("points"))
    if err:
        return json.dumps({"ok": False, "reason": err})

    threshold = float(a.get("threshold", 0.01))
    n_iters = int(a.get("n_iters", 200))
    seed = int(a.get("seed", 42))

    result = ransac_fit_sphere(pts, threshold=threshold, n_iters=n_iters, seed=seed)
    if not result["ok"]:
        return json.dumps(result)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: scan_fit_cylinder
# ---------------------------------------------------------------------------

_scan_fit_cylinder_spec = ToolSpec(
    name="scan_fit_cylinder",
    description=(
        "Fit a cylinder to a point cloud using RANSAC + PCA axis + 2-D circle fit.\n"
        "\n"
        "Algorithm:\n"
        "  1. Estimate cylinder axis via PCA (direction of maximum spread).\n"
        "  2. Project points onto the plane perpendicular to the axis.\n"
        "  3. Fit a 2-D circle (algebraic LS) on the projected points.\n"
        "\n"
        "Minimum 6 points required.\n"
        "\n"
        "Output: {ok, primitive:'cylinder', axis:[ax,ay,az], "
        "axis_point:[x,y,z], radius, inlier_ratio, residual}.\n"
        "'axis' is a unit vector along the cylinder axis.\n"
        "'axis_point' is a point on the axis.\n"
        "\n"
        "RANSAC is deterministic: same points + same seed → same result.\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "points": _POINTS_PROP,
            "threshold": {
                "type": "number",
                "description": (
                    "Maximum radial distance error to count as inlier "
                    "(same units as points). Default 0.01."
                ),
            },
            "n_iters": {
                "type": "integer",
                "description": "Number of RANSAC iterations. Default 200.",
            },
            "seed": {
                "type": "integer",
                "description": "Random seed for reproducibility. Default 42.",
            },
        },
        "required": ["points"],
    },
)


@register(_scan_fit_cylinder_spec, write=False)
async def run_scan_fit_cylinder(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    pts, err = _parse_points(a.get("points"))
    if err:
        return json.dumps({"ok": False, "reason": err})

    threshold = float(a.get("threshold", 0.01))
    n_iters = int(a.get("n_iters", 200))
    seed = int(a.get("seed", 42))

    result = ransac_fit_cylinder(pts, threshold=threshold, n_iters=n_iters, seed=seed)
    if not result["ok"]:
        return json.dumps(result)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: scan_segment
# ---------------------------------------------------------------------------

_scan_segment_spec = ToolSpec(
    name="scan_segment",
    description=(
        "Greedy multi-primitive segmentation of a mixed point cloud.\n"
        "\n"
        "Iteratively finds the dominant primitive (plane, sphere, or cylinder) "
        "in the remaining unassigned points and peels it off, until no more "
        "primitives with ≥ min_inlier_ratio of remaining points can be found.\n"
        "\n"
        "Output: {ok, segments: [{primitive, inlier_count, residual, "
        "...fit params...}], unassigned_count, total_count}.\n"
        "\n"
        "Each segment contains the same fields as the corresponding scan_fit_* "
        "output (normal+d+centre for plane; centre+radius for sphere; "
        "axis+axis_point+radius for cylinder).\n"
        "\n"
        "Use 'primitives' to restrict which types to search for "
        "(e.g. ['plane'] to find only planes).\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "points": _POINTS_PROP,
            "primitives": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["plane", "sphere", "cylinder"],
                },
                "description": (
                    "Which primitive types to search for. "
                    "Default: ['plane', 'sphere', 'cylinder']."
                ),
            },
            "threshold": {
                "type": "number",
                "description": (
                    "Inlier distance threshold (same units as points). Default 0.01."
                ),
            },
            "min_inlier_ratio": {
                "type": "number",
                "description": (
                    "Minimum fraction of remaining points a primitive must "
                    "explain to be accepted. Default 0.1 (10%)."
                ),
            },
            "seed": {
                "type": "integer",
                "description": "Random seed. Default 42.",
            },
        },
        "required": ["points"],
    },
)


@register(_scan_segment_spec, write=False)
async def run_scan_segment(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    pts, err = _parse_points(a.get("points"))
    if err:
        return json.dumps({"ok": False, "reason": err})

    primitives = a.get("primitives", None)
    if primitives is not None and not isinstance(primitives, list):
        return json.dumps({"ok": False, "reason": "'primitives' must be a list"})

    threshold = float(a.get("threshold", 0.01))
    min_inlier_ratio = float(a.get("min_inlier_ratio", 0.1))
    seed = int(a.get("seed", 42))

    result = greedy_segment(
        pts,
        primitives=primitives,
        threshold=threshold,
        min_inlier_ratio=min_inlier_ratio,
        seed=seed,
    )
    if not result["ok"]:
        return json.dumps(result)
    return ok_payload(result)
