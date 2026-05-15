"""
kerf_cad_core.civil.alignment_tools — LLM tool wrappers for road alignment.

Registers four tools with the Kerf tool registry:

  align_horizontal   — Tangent–circular-curve–tangent geometry (PC, PT,
                       arc length, tangent, external, chord, superelevation).
  align_spiral       — Spiralled alignment with clothoid transitions
                       (TS, SC, CS, ST stations + circular arc).
  align_vertical     — Parabolic vertical curve (PVC/PVI/PVT, K-value,
                       high/low point, sight-distance check).
  align_station_at   — Elevation at any station within a parabolic vertical curve.

All tools are pure-Python; no OCC dependency.  Inputs are validated and
errors returned as {ok: false, reason: "..."} — tools never raise.

Units: metres (m), degrees (°), decimal grades, km/h design speed.
Author: imranparuk
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.civil.alignment import (
    compute_horizontal_curve,
    compute_spiral_curve,
    compute_vertical_curve,
    elevation_at,
    parse_station,
)


# ---------------------------------------------------------------------------
# Tool: align_horizontal
# ---------------------------------------------------------------------------

_horiz_spec = ToolSpec(
    name="align_horizontal",
    description=(
        "Compute a tangent–circular-curve–tangent horizontal road alignment.\n"
        "\n"
        "Given the intersection (deflection) angle at the PI, the curve radius, "
        "and the PI station, this tool returns all standard circular-curve "
        "geometry: PC, PT stations, arc length, tangent length, external "
        "distance, middle ordinate, long chord, and degree of curve.\n"
        "\n"
        "Optionally provide design_speed_kmh to get an AASHTO superelevation "
        "hint (e + f method, Table 3-7; e clamped to 12% max).\n"
        "\n"
        "AASHTO relations used:\n"
        "  L = R·Δ  (arc length, Δ in radians)\n"
        "  T = R·tan(Δ/2)\n"
        "  E = R·(sec(Δ/2)−1)\n"
        "  M = R·(1−cos(Δ/2))\n"
        "  C = 2·R·sin(Δ/2)\n"
        "  D = 5729.578/R  (degree of curve)\n"
        "\n"
        "Errors returned as {ok: false, reason: '...'}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "delta_deg": {
                "type": "number",
                "description": (
                    "Intersection (deflection) angle at PI in degrees (0 < delta < 360)."
                ),
            },
            "radius_m": {
                "type": "number",
                "description": "Radius of circular curve in metres (> 0).",
            },
            "sta_pi": {
                "type": "string",
                "description": (
                    "Station of the PI as a string, e.g. '12+34.56' or '1234.56'."
                ),
            },
            "design_speed_kmh": {
                "type": "number",
                "description": (
                    "Design speed in km/h for superelevation hint (AASHTO e+f). "
                    "Omit or set 0 to skip."
                ),
            },
        },
        "required": ["delta_deg", "radius_m", "sta_pi"],
    },
)


@register(_horiz_spec, write=False)
async def run_align_horizontal(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    delta_deg = a.get("delta_deg")
    radius_m = a.get("radius_m")
    sta_pi_str = a.get("sta_pi")
    design_speed = float(a.get("design_speed_kmh", 0.0))

    if delta_deg is None:
        return json.dumps({"ok": False, "reason": "delta_deg is required"})
    if radius_m is None:
        return json.dumps({"ok": False, "reason": "radius_m is required"})
    if sta_pi_str is None:
        return json.dumps({"ok": False, "reason": "sta_pi is required"})

    try:
        delta_deg = float(delta_deg)
        radius_m = float(radius_m)
    except (TypeError, ValueError) as exc:
        return json.dumps({"ok": False, "reason": f"numeric parse error: {exc}"})

    sta_pi_m = parse_station(str(sta_pi_str))
    if math.isnan(sta_pi_m):
        return json.dumps({"ok": False, "reason": f"could not parse sta_pi: {sta_pi_str!r}"})

    result = compute_horizontal_curve(
        delta_deg=delta_deg,
        radius_m=radius_m,
        sta_pi_m=sta_pi_m,
        design_speed_kmh=design_speed,
    )
    if not result.ok:
        return json.dumps({"ok": False, "reason": result.reason})

    payload = asdict(result)
    payload["ok"] = True
    return ok_payload(payload)


# ---------------------------------------------------------------------------
# Tool: align_spiral
# ---------------------------------------------------------------------------

_spiral_spec = ToolSpec(
    name="align_spiral",
    description=(
        "Compute a spiralled horizontal alignment with clothoid (Euler spiral) "
        "transitions.\n"
        "\n"
        "Transitions are placed symmetrically: entry spiral (TS→SC), "
        "circular arc (SC→CS), exit spiral (CS→ST).\n"
        "\n"
        "Clothoid geometry (AASHTO / Hickerson):\n"
        "  θs = Ls/(2·R)                  (spiral angle)\n"
        "  p  = Ls²/(24·R)               (p-shift, radial offset)\n"
        "  k  = Ls/2 − Ls³/(240·R²)      (tangent offset)\n"
        "  Ts = (R+p)·tan(Δ/2) + k       (PI→TS tangent)\n"
        "  Lc = R·(Δ−2·θs)               (circular arc)\n"
        "\n"
        "Errors returned as {ok: false, reason: '...'}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "delta_deg": {
                "type": "number",
                "description": "Deflection angle at PI in degrees (> 0).",
            },
            "radius_m": {
                "type": "number",
                "description": "Radius of circular curve in metres (> 0).",
            },
            "spiral_length_m": {
                "type": "number",
                "description": "Length of each transition spiral (metres, > 0).",
            },
            "sta_pi": {
                "type": "string",
                "description": "Station of PI, e.g. '25+00.00'.",
            },
        },
        "required": ["delta_deg", "radius_m", "spiral_length_m", "sta_pi"],
    },
)


@register(_spiral_spec, write=False)
async def run_align_spiral(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    delta_deg = a.get("delta_deg")
    radius_m = a.get("radius_m")
    spiral_length_m = a.get("spiral_length_m")
    sta_pi_str = a.get("sta_pi")

    for name, val in [("delta_deg", delta_deg), ("radius_m", radius_m),
                      ("spiral_length_m", spiral_length_m), ("sta_pi", sta_pi_str)]:
        if val is None:
            return json.dumps({"ok": False, "reason": f"{name} is required"})

    try:
        delta_deg = float(delta_deg)
        radius_m = float(radius_m)
        spiral_length_m = float(spiral_length_m)
    except (TypeError, ValueError) as exc:
        return json.dumps({"ok": False, "reason": f"numeric parse error: {exc}"})

    sta_pi_m = parse_station(str(sta_pi_str))
    if math.isnan(sta_pi_m):
        return json.dumps({"ok": False, "reason": f"could not parse sta_pi: {sta_pi_str!r}"})

    result = compute_spiral_curve(
        delta_deg=delta_deg,
        radius_m=radius_m,
        spiral_length_m=spiral_length_m,
        sta_pi_m=sta_pi_m,
    )
    if not result.ok:
        return json.dumps({"ok": False, "reason": result.reason})

    payload = asdict(result)
    payload["ok"] = True
    return ok_payload(payload)


# ---------------------------------------------------------------------------
# Tool: align_vertical
# ---------------------------------------------------------------------------

_vert_spec = ToolSpec(
    name="align_vertical",
    description=(
        "Compute a parabolic vertical curve for road alignment.\n"
        "\n"
        "Given back-tangent grade G1, forward-tangent grade G2, the PVI station "
        "and elevation, and curve length L, this tool returns:\n"
        "  - PVC, PVI, PVT stations and elevations\n"
        "  - K-value (L/A where A = |G2−G1| in %)\n"
        "  - Crest or sag classification\n"
        "  - High/low point station and elevation (when G1·G2 < 0)\n"
        "  - Optional AASHTO sight-distance check\n"
        "\n"
        "Parabolic elevation formula (AASHTO):\n"
        "  e(x) = e_PVC + G1·x + (G2−G1)/(2·L)·x²\n"
        "\n"
        "SSD K_min (AASHTO, S≤L):\n"
        "  Crest: K_req = S²/(404+3.5·S)\n"
        "  Sag:   K_req = S²/(120+3.5·S)\n"
        "\n"
        "Errors returned as {ok: false, reason: '...'}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "grade1": {
                "type": "number",
                "description": "Back-tangent grade (decimal, e.g. 0.04 = +4%).",
            },
            "grade2": {
                "type": "number",
                "description": "Forward-tangent grade (decimal).",
            },
            "sta_pvi": {
                "type": "string",
                "description": "Station of PVI, e.g. '10+00.00'.",
            },
            "elev_pvi_m": {
                "type": "number",
                "description": "Elevation of PVI in metres.",
            },
            "curve_length_m": {
                "type": "number",
                "description": "Length of vertical curve in metres (> 0).",
            },
            "stopping_sight_distance_m": {
                "type": "number",
                "description": (
                    "Stopping sight distance (metres) for AASHTO K check. "
                    "Omit or 0 to skip."
                ),
            },
        },
        "required": ["grade1", "grade2", "sta_pvi", "elev_pvi_m", "curve_length_m"],
    },
)


@register(_vert_spec, write=False)
async def run_align_vertical(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    grade1 = a.get("grade1")
    grade2 = a.get("grade2")
    sta_pvi_str = a.get("sta_pvi")
    elev_pvi_m = a.get("elev_pvi_m")
    curve_length_m = a.get("curve_length_m")
    ssd = float(a.get("stopping_sight_distance_m", 0.0))

    for name, val in [("grade1", grade1), ("grade2", grade2),
                      ("sta_pvi", sta_pvi_str), ("elev_pvi_m", elev_pvi_m),
                      ("curve_length_m", curve_length_m)]:
        if val is None:
            return json.dumps({"ok": False, "reason": f"{name} is required"})

    try:
        grade1 = float(grade1)
        grade2 = float(grade2)
        elev_pvi_m = float(elev_pvi_m)
        curve_length_m = float(curve_length_m)
    except (TypeError, ValueError) as exc:
        return json.dumps({"ok": False, "reason": f"numeric parse error: {exc}"})

    sta_pvi_m = parse_station(str(sta_pvi_str))
    if math.isnan(sta_pvi_m):
        return json.dumps({"ok": False, "reason": f"could not parse sta_pvi: {sta_pvi_str!r}"})

    result = compute_vertical_curve(
        grade1=grade1,
        grade2=grade2,
        sta_pvi_m=sta_pvi_m,
        curve_length_m=curve_length_m,
        elev_pvi_m=elev_pvi_m,
        stopping_sight_distance_m=ssd,
    )
    if not result.ok:
        return json.dumps({"ok": False, "reason": result.reason})

    payload = asdict(result)
    payload["ok"] = True
    return ok_payload(payload)


# ---------------------------------------------------------------------------
# Tool: align_station_at
# ---------------------------------------------------------------------------

_sta_at_spec = ToolSpec(
    name="align_station_at",
    description=(
        "Return the parabolic elevation at any station within a vertical curve.\n"
        "\n"
        "Provide the curve parameters (PVC station/elevation, grades, length) "
        "and a query station; the tool returns the elevation.\n"
        "\n"
        "Formula: e(x) = e_PVC + G1·x + (G2−G1)/(2·L)·x²\n"
        "where x = query_station − PVC_station.\n"
        "\n"
        "Errors returned as {ok: false, reason: '...'}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "sta_pvc": {
                "type": "string",
                "description": "Station of PVC, e.g. '09+50.00'.",
            },
            "elev_pvc_m": {
                "type": "number",
                "description": "Elevation at PVC in metres.",
            },
            "grade1": {
                "type": "number",
                "description": "Back-tangent grade (decimal).",
            },
            "grade2": {
                "type": "number",
                "description": "Forward-tangent grade (decimal).",
            },
            "curve_length_m": {
                "type": "number",
                "description": "Curve length in metres (> 0).",
            },
            "query_sta": {
                "type": "string",
                "description": "Query station, e.g. '10+00.00'.",
            },
        },
        "required": ["sta_pvc", "elev_pvc_m", "grade1", "grade2", "curve_length_m", "query_sta"],
    },
)


@register(_sta_at_spec, write=False)
async def run_align_station_at(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    sta_pvc_str = a.get("sta_pvc")
    elev_pvc_m = a.get("elev_pvc_m")
    grade1 = a.get("grade1")
    grade2 = a.get("grade2")
    curve_length_m = a.get("curve_length_m")
    query_sta_str = a.get("query_sta")

    for name, val in [("sta_pvc", sta_pvc_str), ("elev_pvc_m", elev_pvc_m),
                      ("grade1", grade1), ("grade2", grade2),
                      ("curve_length_m", curve_length_m), ("query_sta", query_sta_str)]:
        if val is None:
            return json.dumps({"ok": False, "reason": f"{name} is required"})

    try:
        elev_pvc_m = float(elev_pvc_m)
        grade1 = float(grade1)
        grade2 = float(grade2)
        curve_length_m = float(curve_length_m)
    except (TypeError, ValueError) as exc:
        return json.dumps({"ok": False, "reason": f"numeric parse error: {exc}"})

    sta_pvc_m = parse_station(str(sta_pvc_str))
    if math.isnan(sta_pvc_m):
        return json.dumps({"ok": False, "reason": f"could not parse sta_pvc: {sta_pvc_str!r}"})

    query_sta_m = parse_station(str(query_sta_str))
    if math.isnan(query_sta_m):
        return json.dumps({"ok": False, "reason": f"could not parse query_sta: {query_sta_str!r}"})

    result = elevation_at(
        sta_pvc_m=sta_pvc_m,
        elev_pvc_m=elev_pvc_m,
        grade1=grade1,
        grade2=grade2,
        curve_length_m=curve_length_m,
        query_sta_m=query_sta_m,
    )
    if not result.get("ok"):
        return json.dumps({"ok": False, "reason": result.get("reason", "unknown error")})

    return ok_payload(result)
