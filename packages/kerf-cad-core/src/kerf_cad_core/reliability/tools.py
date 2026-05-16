"""
kerf_cad_core.reliability.tools — LLM tool wrappers for systems reliability & risk analysis.

Registers the following tools with the Kerf tool registry:

  reliability_weibull_fit          — fit Weibull params from failure/censored data
  reliability_weibull_b_life       — Weibull B-life (B10/B50)
  reliability_weibull_mttf         — Weibull MTTF & characteristic life
  reliability_weibull_eval         — Weibull reliability & hazard at time t
  reliability_exponential_mtbf_ci  — exponential MTBF chi-square confidence interval
  reliability_system               — series / parallel / k-out-of-n / bridge
  reliability_availability         — availability (MTBF/MTTR) & redundancy gain
  reliability_stress_strength      — stress-strength interference (normal or numeric)
  reliability_fmea_rpn             — FMEA RPN (S×O×D) & criticality
  reliability_fault_tree           — fault-tree top-event probability, cut sets, importance
  reliability_allocation           — reliability allocation (equal / AGREE)
  reliability_accel_life           — accelerated-life factor (Arrhenius / inverse-power)

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
O'Connor & Kleyner, "Practical Reliability Engineering", 5th ed.
Tobias & Trindade, "Applied Reliability", 3rd ed.
MIL-HDBK-217F, MIL-STD-1629A, IEC 60812, IEC 61025

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.reliability.analysis import (
    weibull_reliability,
    weibull_hazard,
    weibull_b_life,
    weibull_mttf,
    weibull_characteristic_life,
    weibull_fit,
    exponential_reliability,
    exponential_mtbf_ci,
    system_series,
    system_parallel,
    system_k_out_of_n,
    system_bridge,
    availability,
    redundancy_gain,
    stress_strength_normal,
    stress_strength_numeric,
    fmea_rpn,
    fmea_criticality,
    fault_tree_top,
    fault_tree_cut_sets,
    fault_tree_importance,
    reliability_allocation_equal,
    reliability_allocation_agree,
    arrhenius_af,
    inverse_power_af,
)


# ---------------------------------------------------------------------------
# Tool: reliability_weibull_fit
# ---------------------------------------------------------------------------

_weibull_fit_spec = ToolSpec(
    name="reliability_weibull_fit",
    description=(
        "Fit a 2-parameter Weibull distribution to failure time data, with optional "
        "right-censored (suspension) times.\n"
        "\n"
        "Supported methods:\n"
        "  'RRX' (default) — Rank-Regression on X (least-squares on ln(t))\n"
        "  'RRY'           — Rank-Regression on Y\n"
        "  'MLE'           — Maximum Likelihood Estimation\n"
        "\n"
        "Median-rank regression uses Benard's approximation with adjusted ranks "
        "for suspended units.\n"
        "\n"
        "Returns beta (shape), eta (scale/characteristic life), gamma (location, "
        "default 0), and R² (for regression methods).\n"
        "\n"
        "Warns if R² < 0.9 (data may not fit Weibull well) or fewer than 2 failures.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "times": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Failure times (all > 0 or > gamma if 3-param). At least 2 required.",
            },
            "censored": {
                "type": "array",
                "items": {"type": "number"},
                "description": (
                    "Right-censored (suspension) times — units removed without failure. "
                    "Optional; default is no censoring."
                ),
            },
            "method": {
                "type": "string",
                "enum": ["RRX", "RRY", "MLE"],
                "description": "Fitting method: 'RRX' (default), 'RRY', or 'MLE'.",
            },
            "gamma": {
                "type": "number",
                "description": "Known location (minimum life) parameter (default 0 — 2-param Weibull).",
            },
        },
        "required": ["times"],
    },
)


@register(_weibull_fit_spec, write=False)
async def run_weibull_fit(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("times") is None:
        return json.dumps({"ok": False, "reason": "times is required"})

    kwargs: dict = {}
    if "censored" in a:
        kwargs["censored"] = a["censored"]
    if "method" in a:
        kwargs["method"] = a["method"]
    if "gamma" in a:
        kwargs["gamma"] = a["gamma"]

    result = weibull_fit(a["times"], **kwargs)
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: reliability_weibull_b_life
# ---------------------------------------------------------------------------

_weibull_b_life_spec = ToolSpec(
    name="reliability_weibull_b_life",
    description=(
        "Compute Weibull B-life: the time by which pct% of units have failed.\n"
        "\n"
        "  t_Bx = gamma + eta * (-ln(1 - x))^(1/beta)   where x = pct/100\n"
        "\n"
        "Common examples:\n"
        "  B10 (pct=10) — time by which 10% of units fail (design life)\n"
        "  B50 (pct=50) — median life\n"
        "\n"
        "Returns t_B in the same units as eta.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "pct": {
                "type": "number",
                "description": "Percentile (0 < pct < 100). E.g. 10 for B10, 50 for B50.",
            },
            "beta": {
                "type": "number",
                "description": "Weibull shape parameter (> 0).",
            },
            "eta": {
                "type": "number",
                "description": "Weibull scale / characteristic life (> 0).",
            },
            "gamma": {
                "type": "number",
                "description": "Location parameter (default 0).",
            },
        },
        "required": ["pct", "beta", "eta"],
    },
)


@register(_weibull_b_life_spec, write=False)
async def run_weibull_b_life(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("pct", "beta", "eta"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "gamma" in a:
        kwargs["gamma"] = a["gamma"]

    result = weibull_b_life(a["pct"], a["beta"], a["eta"], **kwargs)
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: reliability_weibull_mttf
# ---------------------------------------------------------------------------

_weibull_mttf_spec = ToolSpec(
    name="reliability_weibull_mttf",
    description=(
        "Compute Weibull MTTF and characteristic life from shape/scale parameters.\n"
        "\n"
        "  MTTF = gamma + eta * Gamma(1 + 1/beta)\n"
        "  Characteristic life t_632 = gamma + eta  (63.2% failure point)\n"
        "\n"
        "Returns mttf and t_632 in the same units as eta.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "beta": {
                "type": "number",
                "description": "Weibull shape parameter (> 0).",
            },
            "eta": {
                "type": "number",
                "description": "Weibull scale / characteristic life (> 0).",
            },
            "gamma": {
                "type": "number",
                "description": "Location parameter (default 0).",
            },
        },
        "required": ["beta", "eta"],
    },
)


@register(_weibull_mttf_spec, write=False)
async def run_weibull_mttf(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("beta", "eta"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "gamma" in a:
        kwargs["gamma"] = a["gamma"]

    r_mttf = weibull_mttf(a["beta"], a["eta"], **kwargs)
    r_cl = weibull_characteristic_life(a["beta"], a["eta"], **kwargs)
    if not r_mttf.get("ok"):
        return json.dumps(r_mttf)
    if not r_cl.get("ok"):
        return json.dumps(r_cl)

    combined = {
        "ok": True,
        "mttf": r_mttf["mttf"],
        "eta": r_cl["eta"],
        "t_632": r_cl["t_632"],
        "warnings": r_mttf["warnings"] + r_cl["warnings"],
    }
    return ok_payload(combined)


# ---------------------------------------------------------------------------
# Tool: reliability_weibull_eval
# ---------------------------------------------------------------------------

_weibull_eval_spec = ToolSpec(
    name="reliability_weibull_eval",
    description=(
        "Evaluate Weibull reliability R(t), unreliability F(t), and hazard rate h(t) "
        "at a given time t.\n"
        "\n"
        "  R(t) = exp(-((t-gamma)/eta)^beta)  [survival probability]\n"
        "  F(t) = 1 - R(t)                    [cumulative failure probability]\n"
        "  h(t) = (beta/eta)*((t-gamma)/eta)^(beta-1)  [instantaneous failure rate]\n"
        "\n"
        "Warns if R(t) < 0.1 (high failure probability).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "t": {
                "type": "number",
                "description": "Evaluation time (must be > gamma). Same units as eta.",
            },
            "beta": {
                "type": "number",
                "description": "Weibull shape parameter (> 0).",
            },
            "eta": {
                "type": "number",
                "description": "Weibull scale / characteristic life (> 0).",
            },
            "gamma": {
                "type": "number",
                "description": "Location parameter (default 0).",
            },
        },
        "required": ["t", "beta", "eta"],
    },
)


@register(_weibull_eval_spec, write=False)
async def run_weibull_eval(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("t", "beta", "eta"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "gamma" in a:
        kwargs["gamma"] = a["gamma"]

    r_rel = weibull_reliability(a["t"], a["beta"], a["eta"], **kwargs)
    r_haz = weibull_hazard(a["t"], a["beta"], a["eta"], **kwargs)
    if not r_rel.get("ok"):
        return json.dumps(r_rel)
    if not r_haz.get("ok"):
        return json.dumps(r_haz)

    combined = {
        "ok": True,
        "R": r_rel["R"],
        "F": r_rel["F"],
        "h": r_haz["h"],
        "warnings": r_rel["warnings"] + r_haz["warnings"],
    }
    return ok_payload(combined)


# ---------------------------------------------------------------------------
# Tool: reliability_exponential_mtbf_ci
# ---------------------------------------------------------------------------

_exp_mtbf_ci_spec = ToolSpec(
    name="reliability_exponential_mtbf_ci",
    description=(
        "Compute chi-square confidence interval on MTBF from observed test data.\n"
        "\n"
        "Assumes a homogeneous Poisson process (exponential life distribution).\n"
        "\n"
        "  MTBF_lower = 2*T / chi2(1-alpha/2, 2*(r+1))\n"
        "  MTBF_upper = 2*T / chi2(alpha/2,   2*r)\n"
        "\n"
        "Also returns point estimate (T/r) and R(t) at one MTBF_lower.\n"
        "\n"
        "Warns if 0 failures (only lower bound meaningful) or narrow interval.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "failures": {
                "type": "integer",
                "description": "Number of observed failures (>= 0).",
            },
            "test_time": {
                "type": "number",
                "description": "Total accumulated test time (> 0, any consistent unit).",
            },
            "confidence": {
                "type": "number",
                "description": "Two-sided confidence level (default 0.90). E.g. 0.90, 0.95.",
            },
        },
        "required": ["failures", "test_time"],
    },
)


@register(_exp_mtbf_ci_spec, write=False)
async def run_exponential_mtbf_ci(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("failures") is None:
        return json.dumps({"ok": False, "reason": "failures is required"})
    if a.get("test_time") is None:
        return json.dumps({"ok": False, "reason": "test_time is required"})

    failures = a["failures"]
    if not isinstance(failures, int):
        try:
            failures = int(failures)
        except (ValueError, TypeError):
            return json.dumps({"ok": False, "reason": "failures must be an integer"})

    kwargs: dict = {}
    if "confidence" in a:
        kwargs["confidence"] = a["confidence"]

    result = exponential_mtbf_ci(failures, a["test_time"], **kwargs)
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: reliability_system
# ---------------------------------------------------------------------------

_system_spec = ToolSpec(
    name="reliability_system",
    description=(
        "Compute system reliability for series, parallel, k-out-of-n, or bridge "
        "configurations.\n"
        "\n"
        "Configurations:\n"
        "  'series'    — R = product(R_i); requires reliabilities list\n"
        "  'parallel'  — R = 1 - product(1-R_i); requires reliabilities list\n"
        "  'k_of_n'    — binomial: R = sum_{i=k}^{n} C(n,i)*r^i*(1-r)^(n-i)\n"
        "                requires k, n, r (all identical components)\n"
        "  'bridge'    — 5-component bridge; requires reliabilities list of 5 values\n"
        "\n"
        "Warns if computed system reliability < 0.5.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "config": {
                "type": "string",
                "enum": ["series", "parallel", "k_of_n", "bridge"],
                "description": "System configuration type.",
            },
            "reliabilities": {
                "type": "array",
                "items": {"type": "number"},
                "description": (
                    "Component reliabilities in [0,1]. "
                    "Required for 'series', 'parallel', 'bridge'."
                ),
            },
            "k": {
                "type": "integer",
                "description": "Minimum number of components that must work (k-of-n only).",
            },
            "n": {
                "type": "integer",
                "description": "Total number of components (k-of-n only).",
            },
            "r": {
                "type": "number",
                "description": "Component reliability in [0,1] (k-of-n only — all identical).",
            },
        },
        "required": ["config"],
    },
)


@register(_system_spec, write=False)
async def run_system(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    config = a.get("config")
    if not config:
        return json.dumps({"ok": False, "reason": "config is required"})

    if config == "series":
        if a.get("reliabilities") is None:
            return json.dumps({"ok": False, "reason": "reliabilities is required for 'series'"})
        result = system_series(a["reliabilities"])
    elif config == "parallel":
        if a.get("reliabilities") is None:
            return json.dumps({"ok": False, "reason": "reliabilities is required for 'parallel'"})
        result = system_parallel(a["reliabilities"])
    elif config == "k_of_n":
        for f in ("k", "n", "r"):
            if a.get(f) is None:
                return json.dumps({"ok": False, "reason": f"{f} is required for 'k_of_n'"})
        result = system_k_out_of_n(int(a["k"]), int(a["n"]), a["r"])
    elif config == "bridge":
        if a.get("reliabilities") is None:
            return json.dumps({"ok": False, "reason": "reliabilities is required for 'bridge'"})
        result = system_bridge(a["reliabilities"])
    else:
        return json.dumps({"ok": False, "reason": f"unknown config: {config!r}"})

    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: reliability_availability
# ---------------------------------------------------------------------------

_availability_spec = ToolSpec(
    name="reliability_availability",
    description=(
        "Compute steady-state availability from MTBF and MTTR, and evaluate "
        "redundancy gain from active or standby parallel units.\n"
        "\n"
        "Availability:\n"
        "  A = MTBF / (MTBF + MTTR)\n"
        "\n"
        "Redundancy gain (optional — set n_active > 1 or n_standby > 0):\n"
        "  R_active   = 1 - (1 - r)^n_active\n"
        "  R_standby  ≈ 1 - (1 - r)^(n_active + n_standby)\n"
        "\n"
        "Warns if availability < 0.9 or active R < 0.9.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "mtbf": {
                "type": "number",
                "description": "Mean time between failures (> 0, any time unit).",
            },
            "mttr": {
                "type": "number",
                "description": "Mean time to repair (> 0, same unit as mtbf).",
            },
            "r": {
                "type": "number",
                "description": (
                    "Component reliability in [0,1] for redundancy calculation. "
                    "Optional — omit to skip redundancy analysis."
                ),
            },
            "n_active": {
                "type": "integer",
                "description": "Number of active parallel components (default 1).",
            },
            "n_standby": {
                "type": "integer",
                "description": "Number of standby (cold/warm) spare units (default 0).",
            },
        },
        "required": ["mtbf", "mttr"],
    },
)


@register(_availability_spec, write=False)
async def run_availability(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("mtbf", "mttr"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    avail_result = availability(a["mtbf"], a["mttr"])
    if not avail_result.get("ok"):
        return json.dumps(avail_result)

    combined = dict(avail_result)

    if a.get("r") is not None:
        n_act = int(a.get("n_active", 1))
        n_stby = int(a.get("n_standby", 0))
        red_result = redundancy_gain(a["r"], n_act, n_standby=n_stby)
        if not red_result.get("ok"):
            return json.dumps(red_result)
        combined["redundancy"] = {
            "R_active": red_result["R_active"],
            "gain_active": red_result["gain_active"],
            "R_with_standby": red_result["R_with_standby"],
            "gain_standby": red_result["gain_standby"],
        }
        combined["warnings"] = combined.get("warnings", []) + red_result.get("warnings", [])

    return ok_payload(combined)


# ---------------------------------------------------------------------------
# Tool: reliability_stress_strength
# ---------------------------------------------------------------------------

_ss_spec = ToolSpec(
    name="reliability_stress_strength",
    description=(
        "Compute reliability via stress-strength interference.\n"
        "\n"
        "Two modes:\n"
        "  'normal' — closed-form P(strength > stress) for normal distributions:\n"
        "    R = Phi(z),  z = (mu_r - mu_s) / sqrt(sigma_r^2 + sigma_s^2)\n"
        "  'numeric' — empirical/Monte-Carlo: R = count(R_i > S_i) / n\n"
        "\n"
        "For 'normal': provide mu_s, sigma_s, mu_r, sigma_r.\n"
        "For 'numeric': provide stress_samples and strength_samples (lists).\n"
        "\n"
        "Warns if R < 0.9 or < 30 samples (numeric).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["normal", "numeric"],
                "description": "Calculation mode: 'normal' (default) or 'numeric'.",
            },
            "mu_s": {
                "type": "number",
                "description": "Mean stress (for mode='normal').",
            },
            "sigma_s": {
                "type": "number",
                "description": "Std dev of stress > 0 (for mode='normal').",
            },
            "mu_r": {
                "type": "number",
                "description": "Mean strength (for mode='normal').",
            },
            "sigma_r": {
                "type": "number",
                "description": "Std dev of strength > 0 (for mode='normal').",
            },
            "stress_samples": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Stress sample values (for mode='numeric').",
            },
            "strength_samples": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Strength sample values (for mode='numeric').",
            },
        },
        "required": [],
    },
)


@register(_ss_spec, write=False)
async def run_stress_strength(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    mode = a.get("mode", "normal")

    if mode == "normal":
        for field in ("mu_s", "sigma_s", "mu_r", "sigma_r"):
            if a.get(field) is None:
                return json.dumps({"ok": False, "reason": f"{field} is required for mode='normal'"})
        result = stress_strength_normal(a["mu_s"], a["sigma_s"], a["mu_r"], a["sigma_r"])
    elif mode == "numeric":
        if a.get("stress_samples") is None:
            return json.dumps({"ok": False, "reason": "stress_samples is required for mode='numeric'"})
        if a.get("strength_samples") is None:
            return json.dumps({"ok": False, "reason": "strength_samples is required for mode='numeric'"})
        result = stress_strength_numeric(a["stress_samples"], a["strength_samples"])
    else:
        return json.dumps({"ok": False, "reason": f"unknown mode: {mode!r}"})

    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: reliability_fmea_rpn
# ---------------------------------------------------------------------------

_fmea_spec = ToolSpec(
    name="reliability_fmea_rpn",
    description=(
        "Compute FMEA Risk Priority Number (RPN) and criticality.\n"
        "\n"
        "RPN = Severity × Occurrence × Detection  (each 1–10)\n"
        "  S=1 minor, S=10 hazardous without warning\n"
        "  O=1 unlikely, O=10 very high failure rate\n"
        "  D=1 certain detection, D=10 no detection possible\n"
        "\n"
        "Risk levels: low (<50), medium (50–99), high (100–199), critical (>=200).\n"
        "\n"
        "Criticality = mode_ratio × severity × occurrence (MIL-STD-1629A simplified).\n"
        "\n"
        "Warnings for RPN >= 100 or >= 200 (critical).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "severity": {
                "type": "integer",
                "description": "Severity rating (1–10).",
            },
            "occurrence": {
                "type": "integer",
                "description": "Occurrence rating (1–10).",
            },
            "detection": {
                "type": "integer",
                "description": "Detection rating (1–10).",
            },
            "mode_ratio": {
                "type": "number",
                "description": (
                    "Fraction of failures attributable to this mode (default 1.0). "
                    "Used for criticality calculation only."
                ),
            },
        },
        "required": ["severity", "occurrence", "detection"],
    },
)


@register(_fmea_spec, write=False)
async def run_fmea_rpn(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("severity", "occurrence", "detection"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    sev = a["severity"]
    occ = a["occurrence"]
    det = a["detection"]
    if not isinstance(sev, int):
        sev = int(sev)
    if not isinstance(occ, int):
        occ = int(occ)
    if not isinstance(det, int):
        det = int(det)

    rpn_result = fmea_rpn(sev, occ, det)
    if not rpn_result.get("ok"):
        return json.dumps(rpn_result)

    kwargs: dict = {}
    if "mode_ratio" in a:
        kwargs["mode_ratio"] = a["mode_ratio"]

    crit_result = fmea_criticality(sev, occ, **kwargs)
    if not crit_result.get("ok"):
        return json.dumps(crit_result)

    combined = {
        "ok": True,
        "RPN": rpn_result["RPN"],
        "severity": sev,
        "occurrence": occ,
        "detection": det,
        "risk_level": rpn_result["risk_level"],
        "criticality": crit_result["criticality"],
        "warnings": rpn_result["warnings"] + crit_result["warnings"],
    }
    return ok_payload(combined)


# ---------------------------------------------------------------------------
# Tool: reliability_fault_tree
# ---------------------------------------------------------------------------

_fault_tree_spec = ToolSpec(
    name="reliability_fault_tree",
    description=(
        "Evaluate a fault tree: top-event probability, minimal cut sets, and "
        "Birnbaum importance of a specified basic event.\n"
        "\n"
        "Tree node format (nested dict):\n"
        "  Basic event: {\"type\": \"basic\", \"id\": \"E1\", \"p\": 0.01}\n"
        "  AND gate:    {\"type\": \"AND\",   \"children\": [...]}\n"
        "  OR gate:     {\"type\": \"OR\",    \"children\": [...]}\n"
        "  k-of-n gate: {\"type\": \"K_OF_N\", \"k\": 2, \"n\": 3, \"p\": 0.01}\n"
        "\n"
        "Returns:\n"
        "  p_top         — top-event failure probability\n"
        "  cut_sets      — list of minimal cut sets (each = list of event IDs)\n"
        "  I_birnbaum    — Birnbaum importance of event_id (if provided)\n"
        "\n"
        "Warns if p_top > 0.01.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "tree": {
                "type": "object",
                "description": "Fault tree root node (nested dict — see description).",
            },
            "event_id": {
                "type": "string",
                "description": (
                    "ID of a basic event for Birnbaum importance computation. "
                    "Optional — omit to skip importance."
                ),
            },
        },
        "required": ["tree"],
    },
)


@register(_fault_tree_spec, write=False)
async def run_fault_tree(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("tree") is None:
        return json.dumps({"ok": False, "reason": "tree is required"})

    tree = a["tree"]

    top_result = fault_tree_top(tree)
    if not top_result.get("ok"):
        return json.dumps(top_result)

    cs_result = fault_tree_cut_sets(tree)
    if not cs_result.get("ok"):
        return json.dumps(cs_result)

    combined: dict = {
        "ok": True,
        "p_top": top_result["p_top"],
        "cut_sets": cs_result["cut_sets"],
        "n_cut_sets": cs_result["n_cut_sets"],
        "warnings": top_result["warnings"] + cs_result["warnings"],
    }

    event_id = a.get("event_id")
    if event_id:
        imp_result = fault_tree_importance(tree, event_id)
        if imp_result.get("ok"):
            combined["I_birnbaum"] = imp_result["I_birnbaum"]
            combined["warnings"] += imp_result["warnings"]
        else:
            combined["importance_error"] = imp_result.get("reason")

    return ok_payload(combined)


# ---------------------------------------------------------------------------
# Tool: reliability_allocation
# ---------------------------------------------------------------------------

_allocation_spec = ToolSpec(
    name="reliability_allocation",
    description=(
        "Allocate system reliability target to individual components/subsystems.\n"
        "\n"
        "Methods:\n"
        "  'equal' — each component gets r_i = r_sys^(1/n)  (series system)\n"
        "  'agree' — AGREE method: allocate proportional to subsystem importance\n"
        "            and complexity (n_i modules, t_i operating time)\n"
        "\n"
        "Returns per-component target reliability and failure rate.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["equal", "agree"],
                "description": "Allocation method: 'equal' (default) or 'agree'.",
            },
            "r_system": {
                "type": "number",
                "description": "Required system reliability in [0,1].",
            },
            "n_components": {
                "type": "integer",
                "description": "Number of components (required for method='equal').",
            },
            "importances": {
                "type": "array",
                "items": {"type": "number"},
                "description": (
                    "Subsystem importance weights (required for method='agree'). "
                    "Need not be normalised — they are normalised internally."
                ),
            },
            "n_i": {
                "type": "array",
                "items": {"type": "integer"},
                "description": (
                    "Number of modules per subsystem (AGREE method, default all 1)."
                ),
            },
            "t_i": {
                "type": "array",
                "items": {"type": "number"},
                "description": (
                    "Operating time per subsystem (AGREE method, default all 1.0)."
                ),
            },
        },
        "required": ["r_system"],
    },
)


@register(_allocation_spec, write=False)
async def run_reliability_allocation(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("r_system") is None:
        return json.dumps({"ok": False, "reason": "r_system is required"})

    method = a.get("method", "equal")

    if method == "equal":
        if a.get("n_components") is None:
            return json.dumps({"ok": False, "reason": "n_components is required for method='equal'"})
        result = reliability_allocation_equal(a["r_system"], int(a["n_components"]))
    elif method == "agree":
        if a.get("importances") is None:
            return json.dumps({"ok": False, "reason": "importances is required for method='agree'"})
        kwargs: dict = {}
        if "n_i" in a:
            kwargs["n_i"] = a["n_i"]
        if "t_i" in a:
            kwargs["t_i"] = a["t_i"]
        result = reliability_allocation_agree(a["r_system"], a["importances"], **kwargs)
    else:
        return json.dumps({"ok": False, "reason": f"unknown method: {method!r}"})

    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: reliability_accel_life
# ---------------------------------------------------------------------------

_accel_spec = ToolSpec(
    name="reliability_accel_life",
    description=(
        "Compute acceleration factor for accelerated life testing (ALT).\n"
        "\n"
        "Models:\n"
        "  'arrhenius'     — thermal degradation (ICs, polymers, batteries):\n"
        "    AF = exp(E_a/k * (1/T_use - 1/T_acc))\n"
        "    k = 8.617e-5 eV/K (Boltzmann constant)\n"
        "  'inverse_power' — non-thermal stress (voltage, vibration, humidity):\n"
        "    AF = (V_acc / V_use)^n\n"
        "\n"
        "AF > 1 means the test accelerates failure (less test time needed).\n"
        "Equivalent life: t_use = AF × t_test.\n"
        "\n"
        "Warns if T_acc <= T_use (Arrhenius) or V_acc <= V_use (inverse_power).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "model": {
                "type": "string",
                "enum": ["arrhenius", "inverse_power"],
                "description": "ALT model: 'arrhenius' (default) or 'inverse_power'.",
            },
            "E_a": {
                "type": "number",
                "description": (
                    "Activation energy (eV). Required for 'arrhenius'. "
                    "Typical: 0.3–1.2 eV. Silicon oxide: ~1.0 eV."
                ),
            },
            "T_use_K": {
                "type": "number",
                "description": "Use/field temperature (Kelvin, > 0). Required for 'arrhenius'.",
            },
            "T_acc_K": {
                "type": "number",
                "description": "Accelerated test temperature (Kelvin, > T_use_K). Required for 'arrhenius'.",
            },
            "V_use": {
                "type": "number",
                "description": "Use-condition stress level (> 0). Required for 'inverse_power'.",
            },
            "V_acc": {
                "type": "number",
                "description": "Accelerated test stress level (> 0, > V_use for AF > 1). Required for 'inverse_power'.",
            },
            "n": {
                "type": "number",
                "description": "Life-stress exponent (> 0). Required for 'inverse_power'. Dielectric: ~3–5.",
            },
        },
        "required": [],
    },
)


@register(_accel_spec, write=False)
async def run_accel_life(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    model = a.get("model", "arrhenius")

    if model == "arrhenius":
        for field in ("E_a", "T_use_K", "T_acc_K"):
            if a.get(field) is None:
                return json.dumps({"ok": False, "reason": f"{field} is required for model='arrhenius'"})
        result = arrhenius_af(a["E_a"], a["T_use_K"], a["T_acc_K"])
    elif model == "inverse_power":
        for field in ("V_use", "V_acc", "n"):
            if a.get(field) is None:
                return json.dumps({"ok": False, "reason": f"{field} is required for model='inverse_power'"})
        result = inverse_power_af(a["V_use"], a["V_acc"], a["n"])
    else:
        return json.dumps({"ok": False, "reason": f"unknown model: {model!r}"})

    return ok_payload(result) if result.get("ok") else json.dumps(result)
