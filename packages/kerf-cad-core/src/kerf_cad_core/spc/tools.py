"""
kerf_cad_core.spc.tools — LLM tool wrappers for SPC control charts.

Registers the following tools with the Kerf tool registry:

  spc_xbar_r_chart  — Shewhart X̄-R chart
  spc_xbar_s_chart  — Shewhart X̄-S chart
  spc_cusum_chart   — Tabular CUSUM chart
  spc_ewma_chart    — EWMA chart
  spc_run_rules     — Nelson / Western Electric run-rule detection

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": False, "reason": "..."} — tools never raise.

References
----------
Montgomery, D.C. (2020). Introduction to Statistical Quality Control, 8th ed.
ASTM E2587-16.
Nelson, L.S. (1984). JQT 16(4): 237-239.

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.spc.charts import (
    xbar_r_chart,
    xbar_s_chart,
    cusum_chart,
    ewma_chart,
    run_rules,
)


# ---------------------------------------------------------------------------
# Tool: spc_xbar_r_chart
# ---------------------------------------------------------------------------

_xbar_r_spec = ToolSpec(
    name="spc_xbar_r_chart",
    description=(
        "Compute a Shewhart X̄-R control chart from individual observations.\n"
        "\n"
        "Observations are grouped into subgroups of size n. Returns:\n"
        "  - Grand mean (x̄̄), average range (R̄)\n"
        "  - UCL/LCL for both X̄ chart and R chart (using ASTM E2587 A2, D3, D4)\n"
        "  - Per-subgroup means and ranges\n"
        "  - List of out-of-control points for X̄ and R\n"
        "  - Estimated process σ = R̄/d2\n"
        "\n"
        "Subgroup size n must be 2–25 (per ASTM E2587 Table 1).\n"
        "Any trailing observations that don't form a complete subgroup are discarded.\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "data": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Individual observations (flat list, grouped internally by n)",
                "minItems": 2,
            },
            "n": {
                "type": "integer",
                "description": "Subgroup size (2–25, per ASTM E2587)",
                "minimum": 2,
                "maximum": 25,
            },
            "ucl_sigma": {
                "type": "number",
                "description": "Control limit multiplier in sigma units (default 3.0)",
            },
        },
        "required": ["data", "n"],
    },
)


@register(_xbar_r_spec, write=False)
async def run_spc_xbar_r(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    data = a.get("data")
    if not isinstance(data, list):
        return err_payload("data must be a list of numbers", "BAD_ARGS")
    n = a.get("n")
    if not isinstance(n, int) or n < 2 or n > 25:
        return err_payload("n must be an integer 2–25", "BAD_ARGS")
    kwargs = {}
    if "ucl_sigma" in a:
        kwargs["ucl_sigma"] = float(a["ucl_sigma"])
    try:
        result = xbar_r_chart(data, n, **kwargs)
    except Exception as exc:
        return err_payload(str(exc), "RUNTIME_ERROR")
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: spc_xbar_s_chart
# ---------------------------------------------------------------------------

_xbar_s_spec = ToolSpec(
    name="spc_xbar_s_chart",
    description=(
        "Compute a Shewhart X̄-S control chart from individual observations.\n"
        "\n"
        "Preferred over X̄-R when subgroup size n > 10.\n"
        "Returns UCL/LCL using ASTM E2587 A3, B3, B4 constants,\n"
        "subgroup means / standard deviations, OOC points, and estimated σ = S̄/c4.\n"
        "\n"
        "Subgroup size n must be 2–25. Trailing incomplete subgroups are dropped.\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "data": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Individual observations",
                "minItems": 2,
            },
            "n": {
                "type": "integer",
                "description": "Subgroup size (2–25)",
                "minimum": 2,
                "maximum": 25,
            },
            "ucl_sigma": {
                "type": "number",
                "description": "Control limit multiplier (default 3.0)",
            },
        },
        "required": ["data", "n"],
    },
)


@register(_xbar_s_spec, write=False)
async def run_spc_xbar_s(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    data = a.get("data")
    if not isinstance(data, list):
        return err_payload("data must be a list of numbers", "BAD_ARGS")
    n = a.get("n")
    if not isinstance(n, int) or n < 2 or n > 25:
        return err_payload("n must be an integer 2–25", "BAD_ARGS")
    kwargs = {}
    if "ucl_sigma" in a:
        kwargs["ucl_sigma"] = float(a["ucl_sigma"])
    try:
        result = xbar_s_chart(data, n, **kwargs)
    except Exception as exc:
        return err_payload(str(exc), "RUNTIME_ERROR")
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: spc_cusum_chart
# ---------------------------------------------------------------------------

_cusum_spec = ToolSpec(
    name="spc_cusum_chart",
    description=(
        "Compute a tabular CUSUM control chart for individual observations.\n"
        "\n"
        "CUSUM (Cumulative Sum) is sensitive to small process shifts (0.5–2σ).\n"
        "Uses the two-sided tabular form with:\n"
        "  C_i+ = max(0, C_{i-1}+ + (x_i - μ₀) - K)   [upper CUSUM]\n"
        "  C_i- = min(0, C_{i-1}- + (x_i - μ₀) + K)   [lower CUSUM]\n"
        "  K = k·σ  (allowance/slack, default k=0.5 → optimal for 1σ shift)\n"
        "  H = h·σ  (decision interval, default h=5.0 → ARL≈370 in control)\n"
        "\n"
        "Optional fast-initial-response (Lucas & Crosier 1982): "
        "initialise C+/C- at ±H/2.\n"
        "If sigma is not provided, it is estimated from the moving range.\n"
        "\n"
        "Returns: target, sigma, K, H, C_pos, C_neg arrays, OOC points.\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "data": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Individual observations",
                "minItems": 2,
            },
            "target": {
                "type": "number",
                "description": "Process target μ₀ (default = data mean)",
            },
            "k": {
                "type": "number",
                "description": "Allowance in sigma units (default 0.5)",
            },
            "h": {
                "type": "number",
                "description": "Decision interval in sigma units (default 5.0)",
            },
            "sigma": {
                "type": "number",
                "description": "Process σ (default = estimated from moving range)",
            },
            "fast_initial_response": {
                "type": "boolean",
                "description": "Enable fast-initial-response headstart (default false)",
            },
        },
        "required": ["data"],
    },
)


@register(_cusum_spec, write=False)
async def run_spc_cusum(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    data = a.get("data")
    if not isinstance(data, list):
        return err_payload("data must be a list of numbers", "BAD_ARGS")
    kwargs = {}
    for key in ("target", "k", "h", "sigma"):
        if key in a:
            kwargs[key] = float(a[key])
    if "fast_initial_response" in a:
        kwargs["fast_initial_response"] = bool(a["fast_initial_response"])
    try:
        result = cusum_chart(data, **kwargs)
    except Exception as exc:
        return err_payload(str(exc), "RUNTIME_ERROR")
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: spc_ewma_chart
# ---------------------------------------------------------------------------

_ewma_spec = ToolSpec(
    name="spc_ewma_chart",
    description=(
        "Compute an EWMA (Exponentially Weighted Moving Average) control chart.\n"
        "\n"
        "EWMA tracks the smoothed series z_i = λ·x_i + (1-λ)·z_{i-1}.\n"
        "Control limits: μ₀ ± L·σ_z  where σ²_z = σ²·λ/(2-λ) (steady-state).\n"
        "\n"
        "λ (lambda): smoothing parameter ∈ (0,1]. Typical: 0.1–0.3.\n"
        "  Smaller λ → more smoothing → detects smaller shifts.\n"
        "L: control limit multiplier (default 3.0).\n"
        "\n"
        "When steady_state=False, uses exact transient variance per point\n"
        "(more conservative at chart start-up, same at steady state).\n"
        "\n"
        "If sigma is not provided, estimated from the moving range.\n"
        "\n"
        "Returns: ewma array, UCL/LCL (list or flat), OOC points.\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "data": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Individual observations",
                "minItems": 1,
            },
            "lam": {
                "type": "number",
                "description": "Smoothing parameter λ ∈ (0,1] (default 0.2)",
            },
            "target": {
                "type": "number",
                "description": "Process target μ₀ (default = data mean)",
            },
            "sigma": {
                "type": "number",
                "description": "Process σ (default = estimated from moving range)",
            },
            "L": {
                "type": "number",
                "description": "Control limit multiplier (default 3.0)",
            },
            "steady_state": {
                "type": "boolean",
                "description": "Use steady-state variance (default true)",
            },
        },
        "required": ["data"],
    },
)


@register(_ewma_spec, write=False)
async def run_spc_ewma(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    data = a.get("data")
    if not isinstance(data, list):
        return err_payload("data must be a list of numbers", "BAD_ARGS")
    kwargs = {}
    for key in ("lam", "target", "sigma", "L"):
        if key in a:
            kwargs[key] = float(a[key])
    if "steady_state" in a:
        kwargs["steady_state"] = bool(a["steady_state"])
    try:
        result = ewma_chart(data, **kwargs)
    except Exception as exc:
        return err_payload(str(exc), "RUNTIME_ERROR")
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: spc_run_rules
# ---------------------------------------------------------------------------

_run_rules_spec = ToolSpec(
    name="spc_run_rules",
    description=(
        "Detect special causes using Nelson run rules 1–8 and Western Electric rules.\n"
        "\n"
        "Nelson rules (Nelson, 1984):\n"
        "  nelson1: any point beyond ±3σ\n"
        "  nelson2: 9 consecutive points same side of center\n"
        "  nelson3: 6 consecutive points monotone (trend)\n"
        "  nelson4: 14 consecutive alternating up/down\n"
        "  nelson5: 2 of 3 consecutive beyond ±2σ (same side)\n"
        "  nelson6: 4 of 5 consecutive beyond ±1σ (same side)\n"
        "  nelson7: 15 consecutive within ±1σ (hugging)\n"
        "  nelson8: 8 consecutive outside ±1σ on both sides\n"
        "\n"
        "Western Electric rules:\n"
        "  weco1: 1 point beyond ±3σ (same as nelson1)\n"
        "  weco2: 2 of 3 consecutive beyond ±2σ (same as nelson5)\n"
        "  weco3: 4 of 5 consecutive beyond ±1σ (same as nelson6)\n"
        "  weco4: 8 consecutive same side of CL\n"
        "\n"
        "If center and sigma are not provided, estimated from the data.\n"
        "Returns violations dict (rule → list of flagged point indices) + any_violation.\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "data": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Individual observations",
                "minItems": 1,
            },
            "center": {
                "type": "number",
                "description": "Center line (default = data mean)",
            },
            "sigma": {
                "type": "number",
                "description": "Process σ (default = estimated from moving range)",
            },
            "rules": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Subset of rules to check, e.g. ['nelson1','nelson2','weco4']. "
                    "If omitted, all rules are checked."
                ),
            },
        },
        "required": ["data"],
    },
)


@register(_run_rules_spec, write=False)
async def run_spc_run_rules(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    data = a.get("data")
    if not isinstance(data, list):
        return err_payload("data must be a list of numbers", "BAD_ARGS")
    kwargs = {}
    if "center" in a:
        kwargs["center"] = float(a["center"])
    if "sigma" in a:
        kwargs["sigma"] = float(a["sigma"])
    if "rules" in a:
        kwargs["rules"] = a["rules"]
    try:
        result = run_rules(data, **kwargs)
    except Exception as exc:
        return err_payload(str(exc), "RUNTIME_ERROR")
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: spc_tol3d_analyze
# ---------------------------------------------------------------------------

_tol3d_spec = ToolSpec(
    name="spc_tol3d_analyze",
    description=(
        "Perform 3D vector-loop tolerance stack-up analysis.\n"
        "\n"
        "Models a spatial dimension chain as a series of 6-DOF contributors "
        "(Δx, Δy, Δz, Δrx, Δry, Δrz) each with a tolerance distribution.\n"
        "\n"
        "Methods:\n"
        "  'worst-case' — arithmetic sum of absolute sensitivities × tolerances\n"
        "  'rss'        — root-sum-square (assumes normal, tol = ±3σ per axis)\n"
        "  'monte-carlo'— seeded deterministic LCG (no numpy)\n"
        "\n"
        "Each contributor dict:\n"
        "  mean         list[6] or float — nominal [x,y,z,rx,ry,rz] (default 0)\n"
        "  tol          list[6] or float — symmetric tolerance half-widths >= 0 (default 0)\n"
        "  direction    int (+1 or -1, default +1)\n"
        "  distribution 'normal' (default) or 'uniform'\n"
        "  label        string (optional)\n"
        "\n"
        "Returns closure vector (6 components), delta_per_axis (±3σ or WC uncertainty),\n"
        "total_position_deviation (||Δx,Δy,Δz||), total_orientation_deviation,\n"
        "and the sensitivity Jacobian.\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "contributors": {
                "type": "array",
                "description": "List of 6-DOF contributor dicts",
                "items": {"type": "object"},
                "minItems": 0,
            },
            "method": {
                "type": "string",
                "enum": ["worst-case", "rss", "monte-carlo"],
                "description": "Analysis method (default 'rss')",
            },
            "n_samples": {
                "type": "integer",
                "description": "Monte-Carlo sample count (default 50000, min 2)",
            },
            "seed": {
                "type": "integer",
                "description": "LCG seed for Monte-Carlo reproducibility (default 42)",
            },
        },
        "required": ["contributors"],
    },
)


@register(_tol3d_spec, write=False)
async def run_spc_tol3d(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    contributors = a.get("contributors")
    if not isinstance(contributors, list):
        return err_payload("contributors must be a list", "BAD_ARGS")
    from kerf_cad_core.tolstack.tol3d import analyze_stack_3d
    kwargs = {}
    if "method" in a:
        kwargs["method"] = a["method"]
    if "n_samples" in a:
        kwargs["n_samples"] = int(a["n_samples"])
    if "seed" in a:
        kwargs["seed"] = int(a["seed"])
    try:
        result = analyze_stack_3d(contributors, **kwargs)
    except Exception as exc:
        return err_payload(str(exc), "RUNTIME_ERROR")
    return ok_payload(result) if result.get("ok") else json.dumps(result)
