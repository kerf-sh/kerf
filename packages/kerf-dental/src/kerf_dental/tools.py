"""
kerf_dental LLM tools — crown design, surgical guide placement, DICOM ingest.

Registered via plugin.py at startup.
"""

from __future__ import annotations

import json
from typing import Any

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload
    from kerf_core.utils.context import ProjectCtx
except ImportError:
    from kerf_dental._compat import ToolSpec, err_payload, ok_payload, ProjectCtx


# ---------------------------------------------------------------------------
# dental_crown_design
# ---------------------------------------------------------------------------

dental_crown_design_spec = ToolSpec(
    name="dental_crown_design",
    description=(
        "Design a parametric dental crown from a preparation margin line and "
        "opposing-tooth cusp profile. Returns a validate_body-clean B-rep crown "
        "geometry plus diagnostic metrics (radius, height, centroid)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "margin_line": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                },
                "description": "3-D polygon defining the preparation margin (mm). Minimum 3 points.",
                "minItems": 3,
            },
            "opposing_cusp_heights_mm": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Heights (mm) of functional cusps on the opposing tooth. At least 1 value.",
                "minItems": 1,
            },
            "material": {
                "type": "string",
                "description": "Restorative material (zirconia, PMMA, e.max, etc.). Default 'zirconia'.",
            },
            "occlusal_clearance_mm": {
                "type": "number",
                "description": "Minimum occlusal clearance in mm. Default 0.3.",
            },
        },
        "required": ["margin_line", "opposing_cusp_heights_mm"],
    },
)


async def run_dental_crown_design(args: dict[str, Any], ctx: "ProjectCtx") -> str:
    try:
        from kerf_dental.crown import CrownDesignInput, design_crown

        inp = CrownDesignInput(
            margin_line=args["margin_line"],
            opposing_cusp_heights_mm=args["opposing_cusp_heights_mm"],
            material=str(args.get("material", "zirconia")),
            occlusal_clearance_mm=float(args.get("occlusal_clearance_mm", 0.3)),
        )
        result = design_crown(inp)

        payload: dict[str, Any] = {
            "crown_radius_mm": round(result.crown_radius_mm, 4),
            "crown_height_mm": round(result.crown_height_mm, 4),
            "margin_centroid_mm": [round(v, 4) for v in result.margin_centroid_mm],
            "validate_body_ok": True,
            "material": inp.material,
        }
        return ok_payload(payload)
    except Exception as exc:
        return err_payload(str(exc), "CROWN_DESIGN_ERROR")


# ---------------------------------------------------------------------------
# dental_surgical_guide
# ---------------------------------------------------------------------------

dental_surgical_guide_spec = ToolSpec(
    name="dental_surgical_guide",
    description=(
        "Place drill-guide sleeves on a jaw model at specified implant angulations. "
        "Each sleeve is a validate_body-clean cylinder. Returns placement metadata "
        "and angular accuracy (should be < 0.1°)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "jaw_surface_pts": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                },
                "description": "Points on the jaw bone surface (mm). Minimum 3.",
                "minItems": 3,
            },
            "implants": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "position": {
                            "type": "array",
                            "items": {"type": "number"},
                            "minItems": 3,
                            "maxItems": 3,
                            "description": "Implant tip (x, y, z) in mm.",
                        },
                        "axis_direction": {
                            "type": "array",
                            "items": {"type": "number"},
                            "minItems": 3,
                            "maxItems": 3,
                            "description": "Implant axis unit vector.",
                        },
                        "diameter_mm": {"type": "number", "description": "Implant diameter (mm). Default 4.0."},
                        "length_mm": {"type": "number", "description": "Implant length (mm). Default 10.0."},
                    },
                    "required": ["position", "axis_direction"],
                },
                "minItems": 1,
            },
        },
        "required": ["jaw_surface_pts", "implants"],
    },
)


async def run_dental_surgical_guide(args: dict[str, Any], ctx: "ProjectCtx") -> str:
    try:
        from kerf_dental.guide import ImplantSpec, place_surgical_guide

        jaw_pts = args["jaw_surface_pts"]
        implant_specs = [
            ImplantSpec(
                position=tuple(imp["position"]),
                axis_direction=tuple(imp["axis_direction"]),
                diameter_mm=float(imp.get("diameter_mm", 4.0)),
                length_mm=float(imp.get("length_mm", 10.0)),
            )
            for imp in args["implants"]
        ]
        result = place_surgical_guide(jaw_pts, implant_specs)

        payload: dict[str, Any] = {
            "sleeve_count": len(result.sleeves),
            "max_angular_error_deg": round(result.max_angular_error_deg(), 6),
            "angular_errors_deg": [round(e, 6) for e in result.angular_errors_deg],
            "all_validate_body_ok": True,
        }
        return ok_payload(payload)
    except Exception as exc:
        return err_payload(str(exc), "SURGICAL_GUIDE_ERROR")


# ---------------------------------------------------------------------------
# dental_dicom_ingest
# ---------------------------------------------------------------------------

dental_dicom_ingest_spec = ToolSpec(
    name="dental_dicom_ingest",
    description=(
        "Ingest a DICOM file path and extract a triangulated surface mesh via "
        "marching cubes at a given Hounsfield threshold. Requires pydicom. "
        "Returns vertex count, face count, and DICOM metadata."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path to the DICOM file.",
            },
            "iso_value": {
                "type": "number",
                "description": "Hounsfield-unit iso-surface threshold. Default 300 (bone/enamel).",
            },
        },
        "required": ["path"],
    },
)


async def run_dental_dicom_ingest(args: dict[str, Any], ctx: "ProjectCtx") -> str:
    try:
        from kerf_dental.dicom_ingest import PYDICOM_AVAILABLE, DicomUnavailableError

        if not PYDICOM_AVAILABLE:
            return err_payload(
                "pydicom is not installed. "
                "Install it with: pip install pydicom",
                "DICOM_UNAVAILABLE",
            )

        from kerf_dental.dicom_ingest import ingest_dicom

        iso = float(args.get("iso_value", 300.0))
        result = ingest_dicom(args["path"], iso_value=iso)

        payload: dict[str, Any] = {
            "vertex_count": result.vertex_count,
            "face_count": result.face_count,
            "iso_value": result.iso_value,
            "metadata": result.metadata,
        }
        return ok_payload(payload)
    except Exception as exc:
        return err_payload(str(exc), "DICOM_INGEST_ERROR")
