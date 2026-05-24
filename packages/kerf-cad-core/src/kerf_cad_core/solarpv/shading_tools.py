"""
kerf_cad_core.solarpv.shading_tools — LLM tool wrappers for partial-shading & bypass-diode modelling.

Registers tools with the Kerf tool registry:

  pv_cell_iv              — single-cell I-V curve (single-diode model)
  pv_module_shaded_iv     — module I-V under partial shading with bypass diodes
  pv_mppt_mismatch_loss   — MPPT mismatch loss for a multi-module string

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
Villalva, M.G., Gazoli, J.R., Filho, E.R. (2009) — comprehensive approach to the
    electrical modelling of photovoltaic modules.
De Soto, W., Klein, S.A., Beckman, W.A. (2006) — improvement and validation of a
    model for PV array performance.

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.solarpv.shading import (
    CellParams,
    pv_cell_params_stc,
    cell_iv_curve,
    module_iv_shaded,
    module_iv_uniform,
    mppt_global,
    mppt_mismatch_loss,
    module_mpp,
)


def _parse_cell_params(a: dict) -> CellParams:
    """Build CellParams from tool args dict, using STC defaults for missing fields."""
    defaults = pv_cell_params_stc()
    return CellParams(
        Iph=float(a.get("Iph", defaults.Iph)),
        Io=float(a.get("Io", defaults.Io)),
        Rs=float(a.get("Rs", defaults.Rs)),
        Rsh=float(a.get("Rsh", defaults.Rsh)),
        n=float(a.get("n", defaults.n)),
        T_K=float(a.get("T_C", 25.0)) + 273.15,
    )


# ---------------------------------------------------------------------------
# Tool: pv_cell_iv
# ---------------------------------------------------------------------------

_cell_iv_spec = ToolSpec(
    name="pv_cell_iv",
    description=(
        "Compute the I-V curve of a single solar cell using the single-diode "
        "(Shockley) model.\n"
        "\n"
        "Model: I = Iph − Io·(exp((V + I·Rs)/(n·Vt)) − 1) − (V + I·Rs)/Rsh\n"
        "Solved by Newton–Raphson iteration at each voltage point.\n"
        "\n"
        "Defaults correspond to one cell of a typical 60-cell, ~255 Wp module "
        "at STC (1000 W/m², 25 °C).\n"
        "\n"
        "Returns: iv_curve (list of {v, i, p}), isc_a, voc_v, mpp {p_w, v_v, i_a}.\n"
        "\n"
        "Errors: {ok:false, reason} for bad inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Iph": {
                "type": "number",
                "description": (
                    "Photo-current (A) at 1000 W/m². Proportional to irradiance. "
                    "Default 9.0 A."
                ),
            },
            "Io": {
                "type": "number",
                "description": "Dark saturation current (A). Default 1.5e-10 A.",
            },
            "Rs": {
                "type": "number",
                "description": "Series resistance per cell (Ω). Default 0.005 Ω.",
            },
            "Rsh": {
                "type": "number",
                "description": "Shunt resistance per cell (Ω). Default 400 Ω.",
            },
            "n": {
                "type": "number",
                "description": "Diode ideality factor (1.0–1.5). Default 1.3.",
            },
            "T_C": {
                "type": "number",
                "description": "Cell temperature (°C). Default 25 °C (STC).",
            },
            "irradiance": {
                "type": "number",
                "description": "Irradiance (W/m²) to scale Iph. Default 1000.",
            },
            "n_pts": {
                "type": "integer",
                "description": "Number of I-V sweep points. Default 100.",
            },
        },
        "required": [],
    },
)


@register(_cell_iv_spec, write=False)
async def run_pv_cell_iv(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    try:
        params = _parse_cell_params(a)
        irr = float(a.get("irradiance", 1000.0))
        if irr != 1000.0:
            params = CellParams(
                Iph=params.Iph * irr / 1000.0,
                Io=params.Io, Rs=params.Rs, Rsh=params.Rsh,
                n=params.n, T_K=params.T_K,
            )
        n_pts = int(a.get("n_pts", 100))
        n_pts = max(10, min(n_pts, 500))

        curve = cell_iv_curve(params, n_pts=n_pts)
        mpp = mppt_global(curve)

        # Compute Isc (V=0) and Voc (I≈0)
        from kerf_cad_core.solarpv.shading import cell_iv_point
        isc = cell_iv_point(0.0, params)
        # Voc: last point where I > 0.001
        voc = 0.0
        for v, i in reversed(curve):
            if i > 0.001:
                voc = v
                break

        iv_out = [{"v": round(v, 5), "i": round(i, 6), "p": round(v * i, 6)} for v, i in curve]
        return ok_payload({
            "isc_a": round(isc, 4),
            "voc_v": round(voc, 4),
            "mpp": {
                "p_w": round(mpp["gmpp_p"], 4),
                "v_v": round(mpp["gmpp_v"], 4),
                "i_a": round(mpp["gmpp_i"], 4),
            },
            "iv_curve": iv_out,
            "n_pts": len(iv_out),
        })
    except Exception as exc:
        return err_payload(f"computation error: {exc}", "COMPUTE_ERR")


# ---------------------------------------------------------------------------
# Tool: pv_module_shaded_iv
# ---------------------------------------------------------------------------

_module_shaded_iv_spec = ToolSpec(
    name="pv_module_shaded_iv",
    description=(
        "Compute the I-V curve of a PV module under partial shading, "
        "modelling per-cell irradiance and bypass diodes.\n"
        "\n"
        "The module has N cells in series, grouped into substrings of "
        "`cells_per_bypass` cells each (default 20 = 3 bypass diodes for a "
        "60-cell module).  Each substring has one bypass diode in anti-parallel.\n"
        "\n"
        "When a shaded substring cannot pass the string current in the forward "
        "direction, its bypass diode conducts, clamping that substring to "
        "−bypass_fwd_v (≈ −0.7 V) rather than deep reverse bias.\n"
        "\n"
        "Input irradiance pattern either as:\n"
        "  - cell_irradiances: explicit list of per-cell W/m² values (length = n_cells)\n"
        "  - shading_pattern: compact spec [{\"cells\": N, \"irradiance\": G}, ...]\n"
        "\n"
        "Returns: iv_curve, mpp {p_w, v_v, i_a}, all_local_maxima, "
        "bypass_diodes_active (count), power_loss_vs_uniform_pct.\n"
        "\n"
        "Errors: {ok:false, reason} for bad inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "n_cells": {
                "type": "integer",
                "description": "Total cells in the module (default 60).",
            },
            "cell_irradiances": {
                "type": "array",
                "items": {"type": "number"},
                "description": (
                    "Per-cell irradiance (W/m²). Length must equal n_cells. "
                    "If omitted, use shading_pattern."
                ),
            },
            "shading_pattern": {
                "type": "array",
                "description": (
                    "Compact shading spec — list of {cells: int, irradiance: float} "
                    "segments.  Total cells must equal n_cells.  "
                    "Example: [{\"cells\": 20, \"irradiance\": 500}, {\"cells\": 40, \"irradiance\": 1000}]"
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "cells": {"type": "integer"},
                        "irradiance": {"type": "number"},
                    },
                    "required": ["cells", "irradiance"],
                },
            },
            "cells_per_bypass": {
                "type": "integer",
                "description": "Cells per bypass-diode substring (default 20).",
            },
            "bypass_fwd_v": {
                "type": "number",
                "description": "Bypass diode forward voltage drop (V, default 0.7).",
            },
            "bypass_diodes": {
                "type": "boolean",
                "description": (
                    "If false, disable bypass diodes entirely (simulate old/damaged module). "
                    "Default true."
                ),
            },
            "Iph": {"type": "number", "description": "Cell photo-current at 1000 W/m² (A). Default 9.0."},
            "Io":  {"type": "number", "description": "Dark saturation current (A). Default 1.5e-10."},
            "Rs":  {"type": "number", "description": "Series resistance per cell (Ω). Default 0.005."},
            "Rsh": {"type": "number", "description": "Shunt resistance per cell (Ω). Default 400."},
            "n":   {"type": "number", "description": "Diode ideality factor. Default 1.3."},
            "T_C": {"type": "number", "description": "Cell temperature (°C). Default 25."},
            "n_pts": {"type": "integer", "description": "I-V sweep points (default 200)."},
        },
        "required": [],
    },
)


@register(_module_shaded_iv_spec, write=False)
async def run_pv_module_shaded_iv(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    try:
        params = _parse_cell_params(a)
        n_cells = int(a.get("n_cells", 60))
        cells_per_bypass = int(a.get("cells_per_bypass", 20))
        bypass_fwd_v = float(a.get("bypass_fwd_v", 0.7))
        bypass_diodes = bool(a.get("bypass_diodes", True))
        n_pts = int(a.get("n_pts", 200))
        n_pts = max(20, min(n_pts, 500))

        # Build per-cell irradiance list
        if "cell_irradiances" in a:
            cell_irr = [float(x) for x in a["cell_irradiances"]]
            if len(cell_irr) != n_cells:
                return err_payload(
                    f"cell_irradiances length {len(cell_irr)} != n_cells {n_cells}",
                    "BAD_ARGS",
                )
        elif "shading_pattern" in a:
            cell_irr = []
            for seg in a["shading_pattern"]:
                cell_irr.extend([float(seg["irradiance"])] * int(seg["cells"]))
            if len(cell_irr) != n_cells:
                return err_payload(
                    f"shading_pattern total cells {len(cell_irr)} != n_cells {n_cells}",
                    "BAD_ARGS",
                )
        else:
            # Default: uniform 1000 W/m²
            cell_irr = [1000.0] * n_cells

        # Without bypass: use a very large bypass_fwd_v so it never triggers
        eff_bypass_v = bypass_fwd_v if bypass_diodes else 1e6

        curve = module_iv_shaded(
            cell_irr, params,
            cells_per_bypass=cells_per_bypass,
            bypass_fwd_v=eff_bypass_v,
            n_pts=n_pts,
        )

        mpp_info = mppt_global(curve)

        # Compare to uniform (unshaded) at max irradiance
        max_irr = max(cell_irr)
        unshaded_curve = module_iv_uniform(n_cells, params, max_irr, n_pts=n_pts)
        unshaded_mpp = mppt_global(unshaded_curve)
        unshaded_p = unshaded_mpp["gmpp_p"]
        shaded_p = mpp_info["gmpp_p"]
        loss_pct = (
            (unshaded_p - shaded_p) / unshaded_p * 100.0
            if unshaded_p > 0 else 0.0
        )

        # Count bypassed substrings at GMPP current
        from kerf_cad_core.solarpv.shading import cell_iv_point as _civ
        gmpp_i = mpp_info["gmpp_i"]
        iph_cells = [params.Iph * (g / 1000.0) for g in cell_irr]
        bypass_count = 0
        for start in range(0, n_cells, cells_per_bypass):
            sub = iph_cells[start : start + cells_per_bypass]
            min_iph = min(sub)
            isc_min = _civ(0.0, CellParams(
                Iph=min_iph, Io=params.Io, Rs=params.Rs,
                Rsh=params.Rsh, n=params.n, T_K=params.T_K,
            ))
            if isc_min < gmpp_i and bypass_diodes:
                bypass_count += 1

        iv_out = [{"v": round(v, 4), "i": round(i, 5), "p": round(v * i, 4)} for v, i in curve]
        local_max_out = [
            {"v": round(d["v"], 4), "i": round(d["i"], 5), "p": round(d["p"], 3)}
            for d in mpp_info["local_maxima"]
        ]

        return ok_payload({
            "mpp": {
                "p_w": round(shaded_p, 3),
                "v_v": round(mpp_info["gmpp_v"], 3),
                "i_a": round(mpp_info["gmpp_i"], 4),
            },
            "unshaded_mpp_p_w": round(unshaded_p, 3),
            "power_loss_vs_uniform_pct": round(loss_pct, 2),
            "bypass_diodes_active": bypass_count,
            "n_local_maxima": len(mpp_info["local_maxima"]),
            "all_local_maxima": local_max_out,
            "iv_curve": iv_out,
        })
    except Exception as exc:
        return err_payload(f"computation error: {exc}", "COMPUTE_ERR")


# ---------------------------------------------------------------------------
# Tool: pv_mppt_mismatch_loss
# ---------------------------------------------------------------------------

_mppt_mismatch_spec = ToolSpec(
    name="pv_mppt_mismatch_loss",
    description=(
        "Compute the MPPT mismatch loss for a string of modules sharing one "
        "MPPT input, where each module may have a different partial-shading "
        "pattern.\n"
        "\n"
        "When modules with different shading patterns are in series on the same "
        "MPPT tracker, the tracker finds one operating point for the whole string "
        "— which is always less than the sum of per-module GMPPs.\n"
        "\n"
        "Each module is described by its shading pattern "
        "({cells_per_bypass, cell_irradiances or shading_pattern, bypass_diodes}).\n"
        "\n"
        "Returns: string_gmpp_p_w, sum_module_gmpp_p_w, mismatch_loss_w, "
        "mismatch_loss_pct, per_module_gmpps.\n"
        "\n"
        "Errors: {ok:false, reason} for bad inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "modules": {
                "type": "array",
                "description": (
                    "List of module shading specs.  Each entry may have: "
                    "n_cells (int, default 60), "
                    "cell_irradiances (list of W/m²), "
                    "shading_pattern (list of {cells, irradiance}), "
                    "cells_per_bypass (default 20), "
                    "bypass_fwd_v (default 0.7), "
                    "bypass_diodes (bool, default true). "
                    "Cell params (Iph, Io, Rs, Rsh, n, T_C) override module-level defaults."
                ),
                "items": {"type": "object"},
            },
            "Iph": {"type": "number", "description": "Default cell photo-current (A). Default 9.0."},
            "Io":  {"type": "number", "description": "Default dark saturation current (A). Default 1.5e-10."},
            "Rs":  {"type": "number", "description": "Default series resistance per cell (Ω). Default 0.005."},
            "Rsh": {"type": "number", "description": "Default shunt resistance per cell (Ω). Default 400."},
            "n":   {"type": "number", "description": "Default diode ideality factor. Default 1.3."},
            "T_C": {"type": "number", "description": "Default cell temperature (°C). Default 25."},
            "n_pts": {"type": "integer", "description": "IV sweep points per module (default 200)."},
        },
        "required": ["modules"],
    },
)


@register(_mppt_mismatch_spec, write=False)
async def run_pv_mppt_mismatch_loss(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if not a.get("modules"):
        return err_payload("modules list is required and must be non-empty", "BAD_ARGS")

    try:
        default_params = _parse_cell_params(a)
        n_pts = int(a.get("n_pts", 200))
        n_pts = max(20, min(n_pts, 500))

        module_curves: list[list[tuple[float, float]]] = []

        for i, mod_spec in enumerate(a["modules"]):
            # Allow per-module cell parameter overrides
            merged = {**a, **mod_spec}  # module spec overrides global defaults
            params = _parse_cell_params(merged)
            n_cells = int(mod_spec.get("n_cells", 60))
            cells_per_bypass = int(mod_spec.get("cells_per_bypass", 20))
            bypass_fwd_v = float(mod_spec.get("bypass_fwd_v", 0.7))
            bypass_diodes = bool(mod_spec.get("bypass_diodes", True))
            eff_bypass_v = bypass_fwd_v if bypass_diodes else 1e6

            if "cell_irradiances" in mod_spec:
                cell_irr = [float(x) for x in mod_spec["cell_irradiances"]]
                if len(cell_irr) != n_cells:
                    return err_payload(
                        f"module {i}: cell_irradiances length {len(cell_irr)} != n_cells {n_cells}",
                        "BAD_ARGS",
                    )
            elif "shading_pattern" in mod_spec:
                cell_irr = []
                for seg in mod_spec["shading_pattern"]:
                    cell_irr.extend([float(seg["irradiance"])] * int(seg["cells"]))
                if len(cell_irr) != n_cells:
                    return err_payload(
                        f"module {i}: shading_pattern total {len(cell_irr)} != n_cells {n_cells}",
                        "BAD_ARGS",
                    )
            else:
                cell_irr = [1000.0] * n_cells

            curve = module_iv_shaded(
                cell_irr, params,
                cells_per_bypass=cells_per_bypass,
                bypass_fwd_v=eff_bypass_v,
                n_pts=n_pts,
            )
            module_curves.append(curve)

        result = mppt_mismatch_loss(module_curves, n_pts=n_pts * 2)

        per_module = [
            {
                "module_index": i,
                "gmpp_p_w": round(g["gmpp_p"], 3),
                "gmpp_v_v": round(g["gmpp_v"], 3),
                "gmpp_i_a": round(g["gmpp_i"], 4),
            }
            for i, g in enumerate(result["module_gmpps"])
        ]

        return ok_payload({
            "string_gmpp_p_w": result["string_gmpp_p_w"],
            "sum_module_gmpp_p_w": result["sum_module_gmpp_p_w"],
            "mismatch_loss_w": result["mismatch_loss_w"],
            "mismatch_loss_pct": result["mismatch_loss_pct"],
            "per_module_gmpps": per_module,
        })
    except Exception as exc:
        return err_payload(f"computation error: {exc}", "COMPUTE_ERR")
