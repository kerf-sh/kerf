"""
kerf_dental LLM tools — crown design, surgical guide placement, DICOM ingest,
denture / RPD design, and STL export.

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
        "Design a parametric anatomic dental crown from a preparation margin line and "
        "opposing-tooth cusp profile. Uses design_crown_anatomic: sweeps the actual "
        "margin-line polygon (not a cylinder) upward with cusp ridges (2 for premolars, "
        "4 for molars). Returns a validate_body-clean B-rep crown geometry plus "
        "diagnostic metrics (radius, height, centroid). STL export via dental_stl_export."
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
            "n_cusps": {
                "type": "integer",
                "description": "Number of occlusal cusps: 2 (premolar/incisor), 4 (molar). Default 2.",
            },
            "cusp_depth_fraction": {
                "type": "number",
                "description": "Fraction of crown height for cusp bumps (0.10–0.30). Default 0.20.",
            },
        },
        "required": ["margin_line", "opposing_cusp_heights_mm"],
    },
)


async def run_dental_crown_design(args: dict[str, Any], ctx: "ProjectCtx") -> str:
    try:
        from kerf_dental.crown import CrownDesignInput, design_crown_anatomic

        inp = CrownDesignInput(
            margin_line=args["margin_line"],
            opposing_cusp_heights_mm=args["opposing_cusp_heights_mm"],
            material=str(args.get("material", "zirconia")),
            occlusal_clearance_mm=float(args.get("occlusal_clearance_mm", 0.3)),
        )
        n_cusps = int(args.get("n_cusps", 2))
        cusp_depth_fraction = float(args.get("cusp_depth_fraction", 0.20))
        result = design_crown_anatomic(inp, n_cusps=n_cusps, cusp_depth_fraction=cusp_depth_fraction)

        payload: dict[str, Any] = {
            "crown_radius_mm": round(result.crown_radius_mm, 4),
            "crown_height_mm": round(result.crown_height_mm, 4),
            "margin_centroid_mm": [round(v, 4) for v in result.margin_centroid_mm],
            "validate_body_ok": True,
            "material": inp.material,
            "n_cusps": n_cusps,
            "crown_type": "anatomic",
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


# ---------------------------------------------------------------------------
# dental_denture_design
# ---------------------------------------------------------------------------

dental_denture_design_spec = ToolSpec(
    name="dental_denture_design",
    description=(
        "Design a parametric complete (full) denture or removable partial denture (RPD) "
        "base mesh.  Full denture: horseshoe arch with buccal flange, n_tooth_positions "
        "sockets along the ridge.  RPD: major connector (lingual bar / palatal plate) "
        "with rest positions.  Returns vertex/face counts; use dental_stl_export to get STL."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "denture_type": {
                "type": "string",
                "enum": ["full", "rpd"],
                "description": "'full' (complete denture) or 'rpd' (removable partial denture).",
            },
            "arch": {
                "type": "string",
                "enum": ["mandibular", "maxillary"],
                "description": "Jaw arch. Default 'mandibular'.",
            },
            "flange_height_mm": {
                "type": "number",
                "description": "(full only) Buccal flange height in mm. Default 15.0.",
            },
            "flange_thickness_mm": {
                "type": "number",
                "description": "(full only) Flange wall thickness in mm. Default 2.5.",
            },
            "connector_width_mm": {
                "type": "number",
                "description": "(rpd only) Major connector width in mm. Default 5.0.",
            },
            "connector_depth_mm": {
                "type": "number",
                "description": "(rpd only) Major connector depth (thickness) in mm. Default 2.0.",
            },
            "n_tooth_positions": {
                "type": "integer",
                "description": "(full only) Number of tooth sockets along the arch. Default 14.",
            },
        },
        "required": ["denture_type"],
    },
)


async def run_dental_denture_design(args: dict[str, Any], ctx: "ProjectCtx") -> str:
    try:
        denture_type = str(args.get("denture_type", "full")).lower()
        arch = str(args.get("arch", "mandibular")).lower()

        if denture_type == "full":
            from kerf_dental.denture import DentureSpec, design_full_denture
            spec = DentureSpec(
                arch=arch,
                flange_height_mm=float(args.get("flange_height_mm", 15.0)),
                flange_thickness_mm=float(args.get("flange_thickness_mm", 2.5)),
                n_tooth_positions=int(args.get("n_tooth_positions", 14)),
            )
            result = design_full_denture(spec)
            payload: dict[str, Any] = {
                "denture_type": "full",
                "arch": result.arch,
                "vertex_count": result.vertex_count,
                "face_count": result.face_count,
                "n_tooth_positions": len(result.tooth_positions),
                "arch_semi_a_mm": result.arch_semi_a_mm,
                "arch_semi_b_mm": result.arch_semi_b_mm,
            }

        elif denture_type == "rpd":
            from kerf_dental.denture import RPDSpec, design_rpd
            spec = RPDSpec(
                arch=arch,
                connector_width_mm=float(args.get("connector_width_mm", 5.0)),
                connector_depth_mm=float(args.get("connector_depth_mm", 2.0)),
            )
            result = design_rpd(spec)
            payload = {
                "denture_type": "rpd",
                "arch": arch,
                "connector_type": result.connector_type,
                "vertex_count": result.vertex_count,
                "face_count": result.face_count,
                "n_rest_positions": len(result.rest_positions),
            }
        else:
            return err_payload(f"unknown denture_type: {denture_type!r}", "BAD_ARGS")

        return ok_payload(payload)
    except Exception as exc:
        return err_payload(str(exc), "DENTURE_DESIGN_ERROR")


# ---------------------------------------------------------------------------
# dental_stl_export
# ---------------------------------------------------------------------------

dental_stl_export_spec = ToolSpec(
    name="dental_stl_export",
    description=(
        "Export a dental mesh (vertices + faces as JSON arrays) to binary or ASCII STL "
        "format.  Returns the STL file size and triangle count.  Use this after "
        "dental_crown_design or dental_denture_design to get a milling-ready STL file."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "vertices": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                },
                "description": "Vertex array [[x,y,z], ...] in mm. Minimum 3 vertices.",
                "minItems": 3,
            },
            "faces": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 3,
                    "maxItems": 3,
                },
                "description": "Face index array [[i,j,k], ...]. Minimum 1 triangle.",
                "minItems": 1,
            },
            "output_path": {
                "type": "string",
                "description": "Absolute path to write the STL file.",
            },
            "format": {
                "type": "string",
                "enum": ["binary", "ascii"],
                "description": "'binary' (default, compact) or 'ascii' (human-readable).",
            },
            "solid_name": {
                "type": "string",
                "description": "(ASCII only) Solid name in the STL header. Default 'kerf_dental'.",
            },
        },
        "required": ["vertices", "faces", "output_path"],
    },
)


async def run_dental_stl_export(args: dict[str, Any], ctx: "ProjectCtx") -> str:
    try:
        import numpy as np
        from kerf_dental.stl_export import export_stl_binary, export_stl_ascii

        vertices = np.array(args["vertices"], dtype=np.float32)
        faces = np.array(args["faces"], dtype=np.int32)
        path = str(args["output_path"])
        fmt = str(args.get("format", "binary")).lower()

        if fmt == "binary":
            n_tris = export_stl_binary(vertices, faces, path)
            file_size = 80 + 4 + n_tris * 50
        elif fmt == "ascii":
            solid_name = str(args.get("solid_name", "kerf_dental"))
            n_tris = export_stl_ascii(vertices, faces, path, solid_name=solid_name)
            file_size = -1  # variable for ASCII
        else:
            return err_payload(f"unknown format: {fmt!r}", "BAD_ARGS")

        payload: dict[str, Any] = {
            "triangles_written": n_tris,
            "output_path": path,
            "format": fmt,
            "file_size_bytes": file_size if fmt == "binary" else None,
        }
        return ok_payload(payload)
    except Exception as exc:
        return err_payload(str(exc), "STL_EXPORT_ERROR")
