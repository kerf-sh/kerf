"""
kerf_cad_core.geotech.liq_tools — LLM tool wrappers for liquefaction triggering
analysis.

Registers five tools with the Kerf tool registry:

  liq_csr           — Cyclic Stress Ratio per Seed & Idriss (1971) / Liao & Whitman
  liq_crr_spt       — Cyclic Resistance Ratio from SPT per Youd et al. (2001)
  liq_crr_cpt       — Cyclic Resistance Ratio from CPT per Robertson & Wride (1998)
  liq_safety_factor — Factor of safety FS_L = CRR / CSR
  liq_settlement    — Post-triggering settlement (Tokimatsu & Seed 1987)

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
Seed, H.B. & Idriss, I.M. (1971). ASCE J. Soil Mech. Found. Div., 97(9).
Liao, S.C. & Whitman, R.V. (1986). ASCE J. Geotech. Eng., 112(3).
Youd, T.L. et al. (2001). ASCE J. Geotech. Geoenviron. Eng., 127(10).
Robertson, P.K. & Wride, C.E. (1998). Can. Geotech. J., 35:442-459.
Tokimatsu, K. & Seed, H.B. (1987). ASCE J. Geotech. Eng., 113(8).

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.geotech.liquefaction import (
    csr_seed_idriss,
    crr_from_spt,
    crr_from_cpt,
    liquefaction_safety_factor,
    post_triggering_settlement,
)


# ---------------------------------------------------------------------------
# Tool: liq_csr
# ---------------------------------------------------------------------------

_liq_csr_spec = ToolSpec(
    name="liq_csr",
    description=(
        "Compute the Cyclic Stress Ratio (CSR) for seismic liquefaction "
        "triggering analysis per Seed & Idriss (1971).\n"
        "\n"
        "CSR = 0.65 · (amax/g) · (σ/σ') · rd · (1/MSF)\n"
        "\n"
        "Stress reduction rd uses Liao & Whitman (1986) linear approximation:\n"
        "  rd = 1 − 0.00765·z       for z < 9.15 m\n"
        "  rd = 1.174 − 0.0267·z   for 9.15 ≤ z < 23 m\n"
        "\n"
        "Magnitude Scaling Factor MSF = 10^2.24 / M^2.56 (Idriss 1999).\n"
        "CSR is divided by MSF to normalise to the M=7.5 reference magnitude.\n"
        "\n"
        "Returns CSR_raw, rd, MSF, CSR_M7.5, warnings.\n"
        "Errors: {ok:false, reason} — never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "amax_g": {
                "type": "number",
                "description": (
                    "Peak ground acceleration as a fraction of g (e.g. 0.20 for 0.2g). "
                    "Must be > 0."
                ),
            },
            "total_stress_kPa": {
                "type": "number",
                "description": "Total vertical stress at the layer depth (kPa). > 0.",
            },
            "effective_stress_kPa": {
                "type": "number",
                "description": (
                    "Effective vertical stress at the layer depth (kPa). > 0. "
                    "Must be ≤ total_stress_kPa."
                ),
            },
            "depth_m": {
                "type": "number",
                "description": "Depth to the liquefiable layer (m). ≥ 0.",
            },
            "M": {
                "type": "number",
                "description": (
                    "Moment magnitude of the design earthquake. "
                    "Recommended range: 5.5–8.5."
                ),
            },
        },
        "required": ["amax_g", "total_stress_kPa", "effective_stress_kPa", "depth_m", "M"],
    },
)


@register(_liq_csr_spec, write=False)
async def run_liq_csr(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("amax_g", "total_stress_kPa", "effective_stress_kPa", "depth_m", "M"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = csr_seed_idriss(
        a["amax_g"],
        a["total_stress_kPa"],
        a["effective_stress_kPa"],
        a["depth_m"],
        a["M"],
    )
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: liq_crr_spt
# ---------------------------------------------------------------------------

_liq_crr_spt_spec = ToolSpec(
    name="liq_crr_spt",
    description=(
        "Compute the Cyclic Resistance Ratio (CRR_7.5) from SPT N-value "
        "per Youd et al. (2001).\n"
        "\n"
        "Steps:\n"
        "  1. Overburden correction: CN = (Pa/σ')^0.5 ≤ 1.7 → (N1)60\n"
        "  2. Fines-content correction Δ(N1)60 (Youd Eqs. 6a/b/c) → (N1)60cs\n"
        "  3. CRR_7.5 = 1/(34−(N1)60cs) + (N1)60cs/135\n"
        "               + 50/(10·(N1)60cs+45)² − 1/200\n"
        "     Valid for (N1)60cs ≤ 30; above that soil is non-liquefiable.\n"
        "\n"
        "Returns N1_60, N1_60cs, CN, delta_N1_60cs, CRR_7.5, liquefiable, warnings.\n"
        "Errors: {ok:false, reason} — never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "N60": {
                "type": "number",
                "description": (
                    "SPT blow count corrected for energy (60% efficiency). ≥ 0."
                ),
            },
            "effective_stress_kPa": {
                "type": "number",
                "description": "Effective overburden stress at the test depth (kPa). > 0.",
            },
            "FC": {
                "type": "number",
                "description": (
                    "Fines content (%) passing #200 sieve. "
                    "Default 0 (clean sand). Range [0, 100]."
                ),
            },
            "Pa": {
                "type": "number",
                "description": "Atmospheric pressure (kPa). Default 101.325.",
            },
        },
        "required": ["N60", "effective_stress_kPa"],
    },
)


@register(_liq_crr_spt_spec, write=False)
async def run_liq_crr_spt(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("N60", "effective_stress_kPa"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "FC" in a:
        kwargs["FC"] = a["FC"]
    if "Pa" in a:
        kwargs["Pa"] = a["Pa"]

    result = crr_from_spt(a["N60"], a["effective_stress_kPa"], **kwargs)
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: liq_crr_cpt
# ---------------------------------------------------------------------------

_liq_crr_cpt_spec = ToolSpec(
    name="liq_crr_cpt",
    description=(
        "Compute the Cyclic Resistance Ratio (CRR_7.5) from CPT cone resistance "
        "per Robertson & Wride (1998).\n"
        "\n"
        "Normalises qc to qc1N (overburden-corrected), classifies soil using "
        "the Ic (soil behaviour type index), applies clean-sand correction Kc, "
        "and computes CRR_7.5 for sand-like soils (Ic ≤ 2.6).\n"
        "\n"
        "Returns qc1N, Ic, Fr_pct, Kc, qc1N_cs, CRR_7.5, sand_like, warnings.\n"
        "Errors: {ok:false, reason} — never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "qc_MPa": {
                "type": "number",
                "description": "Measured cone tip resistance (MPa). > 0.",
            },
            "effective_stress_kPa": {
                "type": "number",
                "description": "Effective vertical stress at the test depth (kPa). > 0.",
            },
            "fs_MPa": {
                "type": "number",
                "description": "Sleeve friction (MPa). ≥ 0.",
            },
            "Pa": {
                "type": "number",
                "description": "Atmospheric pressure (MPa). Default 0.101325 MPa.",
            },
        },
        "required": ["qc_MPa", "effective_stress_kPa", "fs_MPa"],
    },
)


@register(_liq_crr_cpt_spec, write=False)
async def run_liq_crr_cpt(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("qc_MPa", "effective_stress_kPa", "fs_MPa"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "Pa" in a:
        kwargs["Pa"] = a["Pa"]

    result = crr_from_cpt(a["qc_MPa"], a["effective_stress_kPa"], a["fs_MPa"], **kwargs)
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: liq_safety_factor
# ---------------------------------------------------------------------------

_liq_safety_factor_spec = ToolSpec(
    name="liq_safety_factor",
    description=(
        "Compute the factor of safety against seismic liquefaction triggering.\n"
        "\n"
        "  FS_L = CRR_7.5 / CSR_M7.5\n"
        "\n"
        "Liquefaction is triggered when FS_L < 1.0.\n"
        "Design practice often requires FS_L ≥ 1.25 (NCEER recommendation).\n"
        "\n"
        "Returns FS_L, liquefied (bool), adequate_for_design (bool), warnings.\n"
        "Errors: {ok:false, reason} — never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "CSR": {
                "type": "number",
                "description": "Cyclic Stress Ratio normalised to M=7.5 (CSR_M7.5). > 0.",
            },
            "CRR": {
                "type": "number",
                "description": "Cyclic Resistance Ratio at M=7.5 (CRR_7.5). > 0.",
            },
            "design_margin": {
                "type": "number",
                "description": (
                    "Design FS threshold (default 1.25 per NCEER). "
                    "FS_L ≥ design_margin means adequate for design."
                ),
            },
        },
        "required": ["CSR", "CRR"],
    },
)


@register(_liq_safety_factor_spec, write=False)
async def run_liq_safety_factor(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("CSR", "CRR"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "design_margin" in a:
        kwargs["design_margin"] = a["design_margin"]

    result = liquefaction_safety_factor(a["CSR"], a["CRR"], **kwargs)
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: liq_settlement
# ---------------------------------------------------------------------------

_liq_settlement_spec = ToolSpec(
    name="liq_settlement",
    description=(
        "Estimate post-triggering settlement of a liquefiable layer using "
        "the Tokimatsu & Seed (1987) volumetric strain chart approximation.\n"
        "\n"
        "  settlement = ε_v (%) × H / 100\n"
        "\n"
        "ε_v is read from the digitised Tokimatsu & Seed (1987) Fig. 5 chart "
        "as a function of CSR_M7.5 and (N1)60.\n"
        "\n"
        "Returns epsilon_v_pct, settlement_m, settlement_mm, warnings.\n"
        "Errors: {ok:false, reason} — never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "CSR": {
                "type": "number",
                "description": "Cyclic Stress Ratio (M=7.5 normalised). > 0.",
            },
            "N1_60": {
                "type": "number",
                "description": "Overburden-corrected SPT blow count (N1)60. ≥ 0.",
            },
            "layer_thickness_m": {
                "type": "number",
                "description": "Thickness of the liquefiable layer (m). > 0.",
            },
        },
        "required": ["CSR", "N1_60", "layer_thickness_m"],
    },
)


@register(_liq_settlement_spec, write=False)
async def run_liq_settlement(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("CSR", "N1_60", "layer_thickness_m"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = post_triggering_settlement(
        a["CSR"], a["N1_60"], a["layer_thickness_m"]
    )
    return ok_payload(result) if result.get("ok") else json.dumps(result)
