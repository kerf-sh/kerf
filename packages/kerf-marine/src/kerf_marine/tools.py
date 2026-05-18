"""
kerf_marine LLM tools — hydrostatics + stability surface for the chat agent.

Tools
-----
marine_hydrostatics     Compute displacement, KB, BM, GM, TPC, MCT1cm from offsets
marine_stability_gz     Compute GZ righting arm curve (wall-sided or KN table)
marine_box_barge        Quick analytic box-barge hydrostatics (no offset table needed)
"""

from __future__ import annotations

import json
from typing import Any

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload
    from kerf_core.utils.context import ProjectCtx
except ImportError:
    from kerf_marine._compat import ToolSpec, err_payload, ok_payload, ProjectCtx


# ---------------------------------------------------------------------------
# marine_hydrostatics
# ---------------------------------------------------------------------------

marine_hydrostatics_spec = ToolSpec(
    name="marine_hydrostatics",
    description=(
        "Compute full hydrostatic properties for a ship hull from an offsets table. "
        "Returns displacement (tonnes), LCB, KB, BM (transverse and longitudinal), "
        "KM, waterplane area, TPC (tonnes per cm immersion), MCT1cm, and LCF. "
        "\n\nOffsets table format: list of [station_m, waterline_m, half_breadth_m] rows. "
        "Stations run from aft (0) to forward. Waterlines run from 0 (keel) to draft. "
        "Half-breadths are half the beam at each (station, waterline) point. "
        "\n\nFor a box barge the analytic formulas hold: "
        "displacement = rho·L·B·T, KB = T/2, BM = B²/(12T)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "offsets": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                },
                "description": "List of [station_m, waterline_m, half_breadth_m] rows.",
            },
            "draft": {
                "type": "number",
                "description": "Waterline draft (m).",
            },
            "rho": {
                "type": "number",
                "description": "Water density t/m³. Default 1.025 (sea water).",
            },
            "kg": {
                "type": "number",
                "description": "Vertical centre of gravity above keel KG (m). Default 0.",
            },
            "method": {
                "type": "string",
                "enum": ["simpson", "trapz"],
                "description": "Integration method. Default 'simpson'.",
            },
        },
        "required": ["offsets", "draft"],
    },
)


async def run_marine_hydrostatics(args: dict[str, Any], ctx: "ProjectCtx") -> str:
    try:
        from kerf_marine.sections import OffsetTable
        from kerf_marine.hydrostatics import compute_hydrostatics, RHO_SW

        offsets = args["offsets"]
        draft = float(args["draft"])
        rho = float(args.get("rho", RHO_SW))
        kg = float(args.get("kg", 0.0))
        method = str(args.get("method", "simpson"))

        table = OffsetTable()
        for row in offsets:
            station, wl, hb = float(row[0]), float(row[1]), float(row[2])
            table.add(station, wl, hb)

        ht = compute_hydrostatics(table, draft, rho=rho, kg=kg, method=method)
        return ok_payload(ht.as_dict())
    except Exception as exc:
        return err_payload(str(exc), "MARINE_HYDROSTATICS_ERROR")


# ---------------------------------------------------------------------------
# marine_box_barge
# ---------------------------------------------------------------------------

marine_box_barge_spec = ToolSpec(
    name="marine_box_barge",
    description=(
        "Compute analytic hydrostatics for a rectangular box barge. "
        "No offset table required — uses exact closed-form formulas: "
        "displacement = rho·L·B·T, KB = T/2, BM = B²/(12T). "
        "Also returns TPC, MCT1cm, waterplane area, LCB, LCF (all at midship)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "length": {
                "type": "number",
                "description": "Length between perpendiculars (m).",
            },
            "beam": {
                "type": "number",
                "description": "Full beam (m).",
            },
            "draft": {
                "type": "number",
                "description": "Even-keel draft (m).",
            },
            "rho": {
                "type": "number",
                "description": "Water density t/m³. Default 1.025 (sea water).",
            },
            "kg": {
                "type": "number",
                "description": "KG above keel (m). Default 0.",
            },
        },
        "required": ["length", "beam", "draft"],
    },
)


async def run_marine_box_barge(args: dict[str, Any], ctx: "ProjectCtx") -> str:
    try:
        from kerf_marine.hydrostatics import box_barge_hydrostatics, RHO_SW

        L = float(args["length"])
        B = float(args["beam"])
        T = float(args["draft"])
        rho = float(args.get("rho", RHO_SW))
        kg = float(args.get("kg", 0.0))

        ht = box_barge_hydrostatics(L, B, T, rho=rho, kg=kg)
        return ok_payload(ht.as_dict())
    except Exception as exc:
        return err_payload(str(exc), "MARINE_BOX_BARGE_ERROR")


# ---------------------------------------------------------------------------
# marine_stability_gz
# ---------------------------------------------------------------------------

marine_stability_gz_spec = ToolSpec(
    name="marine_stability_gz",
    description=(
        "Compute the GZ righting arm curve and intact stability criteria. "
        "Two modes: "
        "\n1. Wall-sided formula (provide gm and bm): "
        "   GZ(φ) = sin(φ)·(GM + ½·BM·tan²(φ)). "
        "\n2. KN table (provide kn_angles, kn_values, kg): "
        "   GZ(φ) = KN(φ) − KG·sin(φ). "
        "\n\nReturns GZ curve points, vanishing angle, area 0–30°, area 0–40°, "
        "area 30–40°, max GZ, and IMO A.749 criteria pass/fail flags."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "gm": {
                "type": "number",
                "description": "Initial metacentric height GM (m). Required for wall-sided mode.",
            },
            "bm": {
                "type": "number",
                "description": "Transverse metacentric radius BM (m). Required for wall-sided mode.",
            },
            "kn_angles": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Heel angles (°) for KN cross-curve table.",
            },
            "kn_values": {
                "type": "array",
                "items": {"type": "number"},
                "description": "KN lever values (m) at each angle.",
            },
            "kg": {
                "type": "number",
                "description": "KG (m) — required for KN-table mode.",
            },
            "angle_step": {
                "type": "number",
                "description": "Step size for GZ evaluation (°). Default 5.",
            },
            "max_angle": {
                "type": "number",
                "description": "Maximum heel angle to evaluate (°). Default 90.",
            },
        },
    },
)


async def run_marine_stability_gz(args: dict[str, Any], ctx: "ProjectCtx") -> str:
    try:
        from kerf_marine.stability import (
            gz_curve_wall_sided, gz_curve_from_kn,
        )

        angle_step = float(args.get("angle_step", 5.0))
        max_angle = float(args.get("max_angle", 90.0))

        if "kn_angles" in args and "kn_values" in args:
            kn_angles = [float(a) for a in args["kn_angles"]]
            kn_values = [float(v) for v in args["kn_values"]]
            kg = float(args.get("kg", 0.0))
            curve = gz_curve_from_kn(kn_angles, kn_values, kg)
        elif "gm" in args and "bm" in args:
            gm = float(args["gm"])
            bm = float(args["bm"])
            curve = gz_curve_wall_sided(
                gm, bm,
                angle_step_deg=angle_step,
                max_angle_deg=max_angle,
            )
        else:
            return err_payload(
                "Provide either (gm, bm) for wall-sided or "
                "(kn_angles, kn_values, kg) for KN-table mode.",
                "MARINE_GZ_BAD_ARGS",
            )

        payload = curve.as_dict()
        payload["imo_criteria"] = curve.imo_criteria()
        return ok_payload(payload)
    except Exception as exc:
        return err_payload(str(exc), "MARINE_GZ_ERROR")
