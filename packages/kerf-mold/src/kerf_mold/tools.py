"""
kerf_mold.tools — LLM tool wrappers for injection-mold tooling.

Registers three tools with the Kerf tool registry:

  mold_check_moldability       — check draft angles, wall uniformity,
                                  parting-surface continuity for a mold design.
  mold_generate_parting_surface — extend a parting-line loop into a flat or
                                  ruled surface patch.
  mold_draft_angle_per_face    — compute signed draft angle for each face.

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
Menges G., Michaeli W., Mohren P. "How to Make Injection Molds", 3rd ed.,
  Hanser 2001.
Rosato D.V., Rosato M.G. "Injection Molding Handbook", 3rd ed.,
  Kluwer Academic 2000.
"""
from __future__ import annotations

import json
from typing import List, Optional

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
    from kerf_core.utils.context import ProjectCtx
    _REGISTRY_AVAILABLE = True
except ImportError:
    from kerf_mold._compat import ToolSpec, err_payload, ok_payload, register, ProjectCtx
    _REGISTRY_AVAILABLE = False

from kerf_mold.mold import (
    Face,
    EjectorPin,
    GateLocation,
    PartingLine,
    MoldDesign,
    check_moldability,
    generate_parting_surface,
    draft_angle_per_face,
)


def _faces_from_args(raw_faces: list) -> tuple:
    """Parse a list of face dicts into Face objects. Returns (faces, error_str)."""
    faces = []
    for i, fd in enumerate(raw_faces):
        if not isinstance(fd, dict):
            return None, f"face[{i}] must be a dict"
        verts = fd.get("vertices")
        normal = fd.get("normal")
        if not verts or not normal:
            return None, f"face[{i}] must have 'vertices' and 'normal'"
        if len(normal) != 3:
            return None, f"face[{i}].normal must be length-3"
        if len(verts) < 3:
            return None, f"face[{i}].vertices must have >= 3 points"
        try:
            face = Face(
                vertices=[[float(x) for x in v[:3]] for v in verts],
                normal=[float(x) for x in normal[:3]],
                face_id=str(fd.get("face_id", f"face_{i}")),
            )
        except Exception as exc:
            return None, f"face[{i}]: {exc}"
        faces.append(face)
    return faces, ""


def _mold_design_from_args(a: dict) -> tuple:
    """Build a MoldDesign from tool args dict. Returns (mold, error_str)."""
    core_raw = a.get("core_faces", [])
    cavity_raw = a.get("cavity_faces", [])
    pl_raw = a.get("parting_line_points")
    pull_raw = a.get("pull_direction")

    if not pl_raw:
        return None, "parting_line_points is required"
    if not pull_raw or len(pull_raw) != 3:
        return None, "pull_direction ([dx,dy,dz]) is required"

    core_faces, err = _faces_from_args(core_raw)
    if core_faces is None:
        return None, f"core_faces: {err}"
    cavity_faces, err = _faces_from_args(cavity_raw)
    if cavity_faces is None:
        return None, f"cavity_faces: {err}"

    try:
        pl = PartingLine(points=[[float(x) for x in p[:3]] for p in pl_raw])
    except Exception as exc:
        return None, f"parting_line_points: {exc}"

    # Optional ejector pins
    ejectors = []
    for j, ep in enumerate(a.get("ejector_pins", [])):
        try:
            ejectors.append(EjectorPin(
                position=[float(x) for x in ep["position"][:3]],
                diameter_mm=float(ep["diameter_mm"]),
                length_mm=float(ep["length_mm"]),
            ))
        except Exception as exc:
            return None, f"ejector_pins[{j}]: {exc}"

    # Optional gate
    gate = None
    gate_raw = a.get("gate")
    if gate_raw:
        try:
            gate = GateLocation(
                point=[float(x) for x in gate_raw["point"][:3]],
                gate_type=gate_raw.get("gate_type", "edge"),
            )
        except Exception as exc:
            return None, f"gate: {exc}"

    wall_t = [float(x) for x in a.get("wall_thicknesses_mm", [])]

    try:
        mold = MoldDesign(
            core_faces=core_faces,
            cavity_faces=cavity_faces,
            parting_line=pl,
            pull_direction=[float(x) for x in pull_raw[:3]],
            ejector_pins=ejectors,
            gate=gate,
            part_name=str(a.get("part_name", "")),
            wall_thicknesses_mm=wall_t,
        )
    except Exception as exc:
        return None, str(exc)

    return mold, ""



# ------------------------------------------------------------------
# Tool: mold_check_moldability
# ------------------------------------------------------------------

_CHECK_SPEC = ToolSpec(
    name="mold_check_moldability",
    description=(
        "Check an injection-mold design for moldability: minimum draft angle per "
        "face, wall-thickness uniformity, and parting-surface planarity relative "
        "to the pull direction.\n\n"
        "Returns: {ok, all_checks_pass, checks{draft_angle, wall_uniformity, "
        "parting_continuity}, failing_faces, warnings}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "core_faces": {
                "type": "array",
                "description": "Core-half faces. Each: {vertices:[[x,y,z],...], normal:[nx,ny,nz], face_id?}.",
                "items": {"type": "object"},
            },
            "cavity_faces": {
                "type": "array",
                "description": "Cavity-half faces.",
                "items": {"type": "object"},
            },
            "parting_line_points": {
                "type": "array",
                "description": "Ordered closed loop of [x,y,z] points forming the parting boundary.",
                "items": {"type": "array", "items": {"type": "number"}},
            },
            "pull_direction": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Mold opening direction [dx, dy, dz] (need not be unit).",
            },
            "min_draft_deg": {
                "type": "number",
                "description": "Minimum acceptable draft angle in degrees (default 1.0).",
            },
            "max_wall_ratio": {
                "type": "number",
                "description": "Maximum acceptable wall thickness max/min ratio (default 3.0).",
            },
            "wall_thicknesses_mm": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Sampled wall thicknesses (mm) for uniformity check. Optional.",
            },
            "ejector_pins": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Optional ejector pins: [{position:[x,y,z], diameter_mm, length_mm}, ...]",
            },
            "gate": {
                "type": "object",
                "description": "Optional gate: {point:[x,y,z], gate_type?}",
            },
            "part_name": {"type": "string"},
        },
        "required": ["parting_line_points", "pull_direction"],
    },
)

@register(_CHECK_SPEC, write=False)
async def run_mold_check_moldability(ctx: "ProjectCtx", args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    mold, err = _mold_design_from_args(a)
    if mold is None:
        return err_payload(err, "BAD_ARGS")

    min_draft = float(a.get("min_draft_deg", 1.0))
    max_ratio = float(a.get("max_wall_ratio", 3.0))
    result = check_moldability(mold, min_draft_deg=min_draft, max_wall_ratio=max_ratio)
    if not result["ok"]:
        return err_payload(result["reason"], "OP_FAILED")
    return ok_payload(result)

# ------------------------------------------------------------------
# Tool: mold_generate_parting_surface
# ------------------------------------------------------------------

_PARTING_SPEC = ToolSpec(
    name="mold_generate_parting_surface",
    description=(
        "Extend a closed parting-line loop into a flat or ruled surface patch.\n\n"
        "'flat' — project all parting-line points onto the best-fit plane and "
        "fan-triangulate from the centroid.\n"
        "'ruled' — extrude each parting-line edge along pull_dir to "
        "extrusion_depth_mm, producing a ruled band.\n\n"
        "Returns: {ok, style, vertices, faces, area_mm2, is_flat, centroid, "
        "warnings}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "parting_line_points": {
                "type": "array",
                "description": "Ordered closed loop of [x,y,z] points.",
                "items": {"type": "array", "items": {"type": "number"}},
            },
            "style": {
                "type": "string",
                "enum": ["flat", "ruled"],
                "description": "'flat' (default) or 'ruled'.",
            },
            "pull_direction": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Required for 'ruled' style: [dx, dy, dz].",
            },
            "extrusion_depth_mm": {
                "type": "number",
                "description": "Ruled extrusion depth in mm (default 50).",
            },
        },
        "required": ["parting_line_points"],
    },
)

@register(_PARTING_SPEC, write=False)
async def run_mold_generate_parting_surface(ctx: "ProjectCtx", args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    pl_raw = a.get("parting_line_points")
    if not pl_raw or len(pl_raw) < 3:
        return err_payload("parting_line_points must have >= 3 points", "BAD_ARGS")

    try:
        pl = PartingLine(points=[[float(x) for x in p[:3]] for p in pl_raw])
    except Exception as exc:
        return err_payload(f"parting_line_points: {exc}", "BAD_ARGS")

    style = str(a.get("style", "flat"))
    pull = a.get("pull_direction")
    depth = float(a.get("extrusion_depth_mm", 50.0))

    result = generate_parting_surface(pl, style=style, pull_dir=pull, extrusion_depth_mm=depth)
    if not result["ok"]:
        return err_payload(result["reason"], "OP_FAILED")
    return ok_payload(result)

# ------------------------------------------------------------------
# Tool: mold_draft_angle_per_face
# ------------------------------------------------------------------

_DRAFT_SPEC = ToolSpec(
    name="mold_draft_angle_per_face",
    description=(
        "Compute signed draft angle (degrees) for each mold face relative to "
        "the pull direction.\n\n"
        "draft_deg = degrees(asin(n · pull_hat))\n"
        "Positive → good draft; negative → undercut; zero → no draft (may stick).\n\n"
        "Returns: list of {face_id, draft_deg, is_undercut, normal} per face. "
        "Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "faces": {
                "type": "array",
                "description": "Faces: [{vertices:[[x,y,z],...], normal:[nx,ny,nz], face_id?}, ...]",
                "items": {"type": "object"},
            },
            "pull_direction": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Mold opening direction [dx, dy, dz].",
            },
        },
        "required": ["faces", "pull_direction"],
    },
)

@register(_DRAFT_SPEC, write=False)
async def run_mold_draft_angle_per_face(ctx: "ProjectCtx", args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    raw_faces = a.get("faces")
    pull = a.get("pull_direction")
    if not raw_faces:
        return err_payload("faces is required and must be non-empty", "BAD_ARGS")
    if not pull or len(pull) != 3:
        return err_payload("pull_direction ([dx,dy,dz]) is required", "BAD_ARGS")

    faces, err = _faces_from_args(raw_faces)
    if faces is None:
        return err_payload(err, "BAD_ARGS")

    results = draft_angle_per_face(faces, pull)
    return ok_payload({"ok": True, "results": results, "num_faces": len(results)})
