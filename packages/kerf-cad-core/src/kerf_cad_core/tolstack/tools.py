"""
kerf_cad_core.tolstack.tools — LLM tool wrappers for tolerance stack-up analysis.

Registers two tools with the Kerf tool registry:

  tolstack_analyze   — run a tolerance stack-up (WC / RSS / MRSS / MC) on a
                       list of dimensional contributors
  tolstack_methods   — describe available stack-up methods

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": False, "reason": "..."} — tools never raise.

References
----------
Dimensioning and Tolerancing Handbook, McGraw-Hill (Drake, 1999)
Bender, A. SAE Technical Paper 680490, 1968.

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.tolstack.stack import analyze_stack


# ---------------------------------------------------------------------------
# Tool: tolstack_analyze
# ---------------------------------------------------------------------------

_tolstack_analyze_spec = ToolSpec(
    name="tolstack_analyze",
    description=(
        "Perform 1D dimensional tolerance stack-up analysis on a list of "
        "dimensional contributors.\n"
        "\n"
        "Four methods are supported:\n"
        "  'worst-case'  — Arithmetic / worst-case (WC): gap_min = nominal - Σtol_i, "
        "gap_max = nominal + Σtol_i.  Conservative; guaranteed to bound every "
        "possible combination.\n"
        "  'rss'         — Root-Sum-Square statistical (RSS, default): assumes each "
        "contributor has a normal distribution with σ_i = tol_i / 3 (i.e. tolerance "
        "represents ±3σ).  Returns ±3σ gap limits, Cp, Cpk, and defect PPM.\n"
        "  'mrss'        — Modified RSS / Benderized (Bender, SAE 680490): applies a "
        "correction factor Cf (default 1.5) to the RSS tolerance sum.  Compensates "
        "for non-normal or mixed distributions.\n"
        "  'monte-carlo' — Monte-Carlo simulation (seeded, deterministic): samples "
        "each contributor from its declared distribution (normal or uniform).  "
        "Returns Cp, Cpk, defect PPM, and yield.  Reproducible via seed.\n"
        "\n"
        "Each contributor dict must have:\n"
        "  nominal      (number) — nominal dimension\n"
        "  plus_tol     (number, >= 0) — upper tolerance magnitude\n"
        "  minus_tol    (number, >= 0) — lower tolerance magnitude\n"
        "  direction    (integer, +1 or -1) — contribution sign in the stack\n"
        "  distribution (string, 'normal' or 'uniform', default 'normal')\n"
        "\n"
        "Asymmetric tolerances are automatically symmetrised with a nominal shift.\n"
        "Degenerate inputs (zero tolerances, empty list) produce warnings, not errors.\n"
        "\n"
        "Returns gap_nominal, gap_min_wc, gap_max_wc (worst-case bounds), "
        "gap_min, gap_max (method-specific ±3σ or MC limits), sigma_gap, "
        "Cp, Cpk, defect_ppm, yield_pct, and a warnings list.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "contributors": {
                "type": "array",
                "description": (
                    "List of dimensional contributor objects. Each object:\n"
                    "  nominal (number) — nominal dimension (any unit)\n"
                    "  plus_tol (number) — upper tolerance magnitude (>= 0)\n"
                    "  minus_tol (number) — lower tolerance magnitude (>= 0)\n"
                    "  direction (integer) — +1 (adds to gap) or -1 (subtracts)\n"
                    "  distribution (string) — 'normal' (default) or 'uniform'"
                ),
                "items": {"type": "object"},
                "minItems": 0,
            },
            "method": {
                "type": "string",
                "enum": ["worst-case", "rss", "mrss", "monte-carlo"],
                "description": (
                    "Stack-up method: 'worst-case', 'rss' (default), "
                    "'mrss' (Benderized), or 'monte-carlo'."
                ),
            },
            "n_samples": {
                "type": "integer",
                "description": (
                    "Number of Monte-Carlo samples (default 100000). "
                    "Only used when method='monte-carlo'. Must be >= 2."
                ),
            },
            "seed": {
                "type": "integer",
                "description": (
                    "LCG seed for Monte-Carlo reproducibility (default 42). "
                    "Same seed + same inputs always yield identical results."
                ),
            },
            "bender_cf": {
                "type": "number",
                "description": (
                    "Bender correction factor for MRSS method (default 1.5). "
                    "Typical range 1.4–1.8. Must be > 0."
                ),
            },
        },
        "required": ["contributors"],
    },
)


@register(_tolstack_analyze_spec, write=False)
async def run_tolstack_analyze(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    contributors = a.get("contributors")
    if contributors is None:
        return json.dumps({"ok": False, "reason": "contributors is required"})

    kwargs: dict = {}
    if "method" in a:
        kwargs["method"] = a["method"]
    if "n_samples" in a:
        kwargs["n_samples"] = a["n_samples"]
    if "seed" in a:
        kwargs["seed"] = a["seed"]
    if "bender_cf" in a:
        kwargs["bender_cf"] = a["bender_cf"]

    result = analyze_stack(contributors, **kwargs)
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: tolstack_methods
# ---------------------------------------------------------------------------

_tolstack_methods_spec = ToolSpec(
    name="tolstack_methods",
    description=(
        "List and describe all available tolerance stack-up analysis methods.\n"
        "\n"
        "Returns a dict of method names → description, typical use case, "
        "and key output fields.  No inputs required.\n"
        "\n"
        "Use this tool to help choose the right method before calling "
        "tolstack_analyze."
    ),
    input_schema={
        "type": "object",
        "properties": {},
        "required": [],
    },
)

_METHODS_INFO = {
    "worst-case": {
        "description": "Arithmetic / worst-case stack. gap_min = nominal - Σtol_i.",
        "use_case": (
            "Safety-critical assemblies where every unit must fit. "
            "100% yield guaranteed if parts meet individual tolerances."
        ),
        "outputs": ["gap_nominal", "gap_min_wc", "gap_max_wc", "gap_min", "gap_max"],
        "statistical": False,
    },
    "rss": {
        "description": (
            "Root-Sum-Square. Assumes normal distribution, σ_i = tol_i / 3. "
            "Returns ±3σ gap, Cp, Cpk, defect PPM."
        ),
        "use_case": (
            "High-volume production with normal process distributions. "
            "Accepts ~0.27% defect rate at ±3σ (2700 ppm)."
        ),
        "outputs": ["gap_nominal", "gap_min", "gap_max", "sigma_gap", "cp", "cpk", "defect_ppm", "yield_pct"],
        "statistical": True,
    },
    "mrss": {
        "description": (
            "Modified RSS / Benderized. gap_tol = Cf × √Σtol_i² (default Cf=1.5). "
            "Corrects for non-normal distributions."
        ),
        "use_case": (
            "Medium-volume assemblies with mixed or mildly non-normal "
            "distributions.  More realistic than pure RSS, less conservative "
            "than worst-case."
        ),
        "outputs": ["gap_nominal", "gap_min", "gap_max", "sigma_gap", "cp", "cpk", "defect_ppm", "yield_pct", "bender_cf"],
        "statistical": True,
    },
    "monte-carlo": {
        "description": (
            "Monte-Carlo simulation (seeded, deterministic LCG, no numpy). "
            "Samples each contributor from its declared distribution. "
            "Default 100 000 samples."
        ),
        "use_case": (
            "Complex stacks with mixed distributions (normal + uniform), "
            "non-linear sensitivities, or when exact distribution shapes matter."
        ),
        "outputs": ["gap_nominal", "gap_min", "gap_max", "sigma_gap", "mean_gap", "cp", "cpk", "defect_ppm", "yield_pct", "n_samples", "seed"],
        "statistical": True,
    },
}


@register(_tolstack_methods_spec, write=False)
async def run_tolstack_methods(ctx: ProjectCtx, args: bytes) -> str:
    return ok_payload({"methods": _METHODS_INFO})
