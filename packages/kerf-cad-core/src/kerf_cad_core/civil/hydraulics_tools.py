"""
kerf_cad_core.civil.hydraulics_tools — LLM tool wrappers for pipe-network
hydraulics and open-channel (Manning) flow analysis.

Registers two tools with the Kerf tool registry:

  hydraulics_pipe_network — Solve a steady-state pressurised pipe network:
                            Hardy-Cross loop method, Hazen-Williams or
                            Darcy-Weisbach head loss.  Reports per-pipe
                            flow/velocity/headloss and per-node pressure.

  hydraulics_manning      — Manning normal-depth for a rectangular open
                            channel / gravity sewer (single reach).

All tools are pure-Python; no OCC dependency.
Inputs validated; errors returned as {ok: false, reason: ...} — never raises.

Units: SI (metres, m³/s, L/s, kPa) unless noted.
Author: imranparuk
"""
from __future__ import annotations

import json
from typing import Any

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.civil.hydraulics import (
    solve_pipe_network,
    manning_normal_depth,
)


# ---------------------------------------------------------------------------
# Tool: hydraulics_pipe_network
# ---------------------------------------------------------------------------

_pipe_network_spec = ToolSpec(
    name="hydraulics_pipe_network",
    description=(
        "Solve a steady-state pressurised pipe network using the Hardy-Cross "
        "iterative loop-correction method.\n"
        "\n"
        "Nodes represent junctions / reservoirs.  Pipes connect nodes and carry "
        "flow from high head to low head.\n"
        "\n"
        "Head-loss formulae available:\n"
        "  'hazen-williams'  — hf = 10.67·L·Q^1.852 / (C^1.852·D^4.87)  (empirical)\n"
        "  'darcy-weisbach'  — hf = f·(L/D)·V²/(2g); f by Colebrook-White iteration\n"
        "\n"
        "At least one node must have 'head_fixed' set (reservoir / tank).\n"
        "\n"
        "Output: {ok, converged, iterations, nodes, pipes, warnings}\n"
        "  nodes[]: {node_id, elevation_m, head_m, pressure_head_m, pressure_kPa, "
        "demand_L_per_s, is_fixed_head}\n"
        "  pipes[]: {pipe_id, start_node, end_node, flow_L_per_s, flow_m3_per_s, "
        "velocity_m_per_s, headloss_m, diameter_m, length_m}\n"
        "\n"
        "Non-convergence is reported in 'warnings' (not raised); results are still "
        "returned as best-effort approximation.\n"
        "\n"
        "Reference: Hardy-Cross (1936), Univ. Illinois Bull. 286; "
        "Hazen-Williams (1905); Colebrook-White (1939)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "nodes": {
                "type": "array",
                "description": (
                    "Network nodes as objects. Each node: "
                    "{node_id: string, elevation: number [m], "
                    "demand: number [L/s, default 0; positive=withdrawal, "
                    "negative=supply], head_fixed: number [m, optional — "
                    "reservoir/tank; omit for junction nodes]}. "
                    "At least one node must have head_fixed."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "node_id": {"type": "string"},
                        "elevation": {"type": "number"},
                        "demand": {"type": "number"},
                        "head_fixed": {"type": "number"},
                    },
                    "required": ["node_id"],
                },
            },
            "pipes": {
                "type": "array",
                "description": (
                    "Pipe segments as objects. Each pipe: "
                    "{pipe_id: string, start_node: string, end_node: string, "
                    "length: number [m], diameter: number [m], "
                    "roughness: number [mm, default 0.1], "
                    "hw_c: number [Hazen-Williams C, default 120]}."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "pipe_id": {"type": "string"},
                        "start_node": {"type": "string"},
                        "end_node": {"type": "string"},
                        "length": {"type": "number"},
                        "diameter": {"type": "number"},
                        "roughness": {"type": "number"},
                        "hw_c": {"type": "number"},
                    },
                    "required": ["pipe_id", "start_node", "end_node", "length", "diameter"],
                },
            },
            "head_loss_method": {
                "type": "string",
                "description": (
                    "Head-loss formula: 'hazen-williams' (default) or "
                    "'darcy-weisbach'. Use Hazen-Williams for water-supply "
                    "networks; Darcy-Weisbach for general pressurised fluids."
                ),
            },
            "max_iterations": {
                "type": "integer",
                "description": "Hardy-Cross iteration cap (default 100).",
            },
            "tolerance_m": {
                "type": "number",
                "description": (
                    "Convergence criterion: max |loop ΔQ| < tolerance_m (default 1e-4 m). "
                    "Tighten for higher precision; loosen for speed."
                ),
            },
        },
        "required": ["nodes", "pipes"],
    },
)


@register(_pipe_network_spec, write=False)
async def run_hydraulics_pipe_network(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    nodes = a.get("nodes")
    pipes = a.get("pipes")
    method = a.get("head_loss_method", "hazen-williams")
    max_iter = int(a.get("max_iterations", 100))
    tol = float(a.get("tolerance_m", 1e-4))

    if not isinstance(nodes, list):
        return json.dumps({"ok": False, "reason": "nodes must be a list"})
    if not isinstance(pipes, list):
        return json.dumps({"ok": False, "reason": "pipes must be a list"})

    result = solve_pipe_network(
        nodes=nodes,
        pipes=pipes,
        head_loss_method=method,
        max_iterations=max_iter,
        tolerance_m=tol,
    )
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: hydraulics_manning
# ---------------------------------------------------------------------------

_manning_spec = ToolSpec(
    name="hydraulics_manning",
    description=(
        "Compute normal depth and hydraulic properties for a rectangular "
        "open channel or gravity sewer using Manning's equation.\n"
        "\n"
        "Manning's equation (SI):  Q = (1/n) · A · R^(2/3) · S^(1/2)\n"
        "  A = width × depth  (m²)\n"
        "  R = A / (width + 2·depth)  (hydraulic radius, m)\n"
        "  S = longitudinal slope (m/m)\n"
        "  n = Manning's roughness coefficient\n"
        "\n"
        "Normal depth is solved by bisection.\n"
        "\n"
        "Output: {ok, normal_depth_m, velocity_m_per_s, flow_area_m2, "
        "wetted_perimeter_m, hydraulic_radius_m, froude_number, flow_regime, "
        "channel_full}.\n"
        "\n"
        "flow_regime: 'subcritical' (Fr < 1), 'critical' (Fr ≈ 1), "
        "'supercritical' (Fr > 1), or 'channel_full' (flow exceeds capacity).\n"
        "\n"
        "Typical Manning's n values: 0.010 smooth PVC, 0.013 concrete, "
        "0.015 brick sewer, 0.025 earth canal, 0.035 vegetated channel.\n"
        "\n"
        "Reference: Manning (1891); Chow (1959) 'Open-Channel Hydraulics'."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "flow_m3s": {
                "type": "number",
                "description": "Design flow rate (m³/s), > 0.",
            },
            "width_m": {
                "type": "number",
                "description": "Channel bottom width (m), > 0.",
            },
            "slope": {
                "type": "number",
                "description": (
                    "Longitudinal slope (m/m), > 0. "
                    "E.g. 0.001 for a 1 in 1000 grade."
                ),
            },
            "manning_n": {
                "type": "number",
                "description": (
                    "Manning's roughness coefficient (dimensionless), > 0. "
                    "Typical: 0.010 PVC, 0.013 concrete, 0.025 earth."
                ),
            },
            "max_depth_m": {
                "type": "number",
                "description": (
                    "Upper depth bound for bisection search (m, default 10.0). "
                    "If the normal depth exceeds this, channel_full=true is "
                    "reported."
                ),
            },
        },
        "required": ["flow_m3s", "width_m", "slope", "manning_n"],
    },
)


@register(_manning_spec, write=False)
async def run_hydraulics_manning(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    flow = a.get("flow_m3s")
    width = a.get("width_m")
    slope = a.get("slope")
    n = a.get("manning_n")
    max_d = float(a.get("max_depth_m", 10.0))

    for name, val in [("flow_m3s", flow), ("width_m", width),
                      ("slope", slope), ("manning_n", n)]:
        if val is None:
            return json.dumps({"ok": False, "reason": f"'{name}' is required"})
        if not isinstance(val, (int, float)):
            return json.dumps({"ok": False, "reason": f"'{name}' must be a number"})

    result = manning_normal_depth(
        flow_m3s=float(flow),
        width_m=float(width),
        slope=float(slope),
        manning_n=float(n),
        max_depth_m=max_d,
    )
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)
