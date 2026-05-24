"""mesh_implicit_tools.py — GK-P46: Wire mesh/implicit ops as LLM ToolSpecs.

Wires the following already-implemented functions into the tool/feature/LLM
surface:

- ``sdf_csg`` + ``marching_cubes``  (GK-P22) — SDF CSG + iso-surface extract
- ``lscm_unwrap`` (GK-P24, ``uv_unwrap.py``) — LSCM UV unwrap
- ``isotropic_remesh`` (GK-P23) — Botsch-Kobbelt isotropic remesh
- ``retopo_snap`` (GK-P25, ``subd_authoring.py``) — snap retopo cage to surface

All ops append a node to a ``.feature`` file; evaluation is pure-Python /
NumPy. No OCCT dispatch.
"""
from __future__ import annotations

import json
import uuid

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx

from kerf_cad_core.surfacing import (
    append_feature_node,
    next_node_id,
    read_feature_content,
)


# ── feature_sdf_csg ───────────────────────────────────────────────────────────
#
# GK-P22: compose SDF primitives with CSG operators and extract a mesh via
# marching cubes.

feature_sdf_csg_spec = ToolSpec(
    name="feature_sdf_csg",
    description=(
        "Append a `sdf_csg` node to a `.feature` file. "
        "Composes SDF (signed-distance-field) primitives using CSG operators "
        "(union / subtract / intersect, with optional smooth-blend radius k) "
        "and extracts a triangulated iso-surface via the Lorensen-Cline "
        "marching-cubes algorithm. "
        "\n\n"
        "**Primitives:** `sphere` (cx,cy,cz,r), `box` (cx,cy,cz,hx,hy,hz), "
        "`cylinder` (cx,cy,cz,r,h — capped, Z-axis). "
        "\n\n"
        "**Ops:** `union` (smooth k>0 → exponential Quilez blend), `subtract`, "
        "`intersect`. "
        "\n\n"
        "**Output:** marching-cubes mesh at the given resolution. "
        "Bounds and resolution control quality vs speed; default resolution 32 "
        "is fast. "
        "No OCCT required — pure-Python + NumPy."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "UUID of the target .feature file.",
            },
            "primitives": {
                "type": "array",
                "description": (
                    "List of SDF primitive descriptors. Each has a `type` "
                    "('sphere', 'box', 'cylinder') and type-specific params."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["sphere", "box", "cylinder"]},
                        "id": {"type": "string"},
                        "cx": {"type": "number"},
                        "cy": {"type": "number"},
                        "cz": {"type": "number"},
                        "r": {"type": "number"},
                        "hx": {"type": "number"},
                        "hy": {"type": "number"},
                        "hz": {"type": "number"},
                        "h": {"type": "number"},
                    },
                    "required": ["type"],
                },
                "minItems": 1,
            },
            "operations": {
                "type": "array",
                "description": (
                    "CSG composition tree. Each entry: "
                    "{op:'union'|'subtract'|'intersect', a:'prim_id', b:'prim_id', k:0.0}. "
                    "References are either primitive ids or prior operation ids. "
                    "The last entry is the root SDF."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "op": {"type": "string", "enum": ["union", "subtract", "intersect"]},
                        "a": {"type": "string"},
                        "b": {"type": "string"},
                        "k": {"type": "number", "default": 0.0},
                    },
                    "required": ["op", "a", "b"],
                },
                "default": [],
            },
            "bounds": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 6,
                "maxItems": 6,
                "description": (
                    "Marching-cubes evaluation bounds as "
                    "[xmin, ymin, zmin, xmax, ymax, zmax]. "
                    "Default: [-10,-10,-10, 10,10,10]."
                ),
            },
            "resolution": {
                "type": "integer",
                "description": "Grid resolution per axis (default 32, max 128).",
                "minimum": 4,
                "maximum": 128,
                "default": 32,
            },
            "isovalue": {
                "type": "number",
                "description": "Iso-surface level (default 0.0 = surface boundary).",
                "default": 0.0,
            },
            "id": {"type": "string", "description": "Optional explicit node id."},
        },
        "required": ["file_id", "primitives"],
    },
)


@register(feature_sdf_csg_spec, write=True)
async def run_feature_sdf_csg(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    primitives = a.get("primitives")
    operations = a.get("operations") or []
    bounds = a.get("bounds") or [-10, -10, -10, 10, 10, 10]
    resolution = a.get("resolution", 32)
    isovalue = a.get("isovalue", 0.0)
    node_id = a.get("id", "").strip()

    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")
    if not isinstance(primitives, list) or len(primitives) == 0:
        return err_payload("primitives must be a non-empty list", "BAD_ARGS")
    for i, p in enumerate(primitives):
        if not isinstance(p, dict) or p.get("type") not in ("sphere", "box", "cylinder"):
            return err_payload(
                f"primitives[{i}].type must be 'sphere', 'box', or 'cylinder'", "BAD_ARGS"
            )
    if not isinstance(bounds, list) or len(bounds) < 6:
        return err_payload("bounds must be [xmin,ymin,zmin,xmax,ymax,zmax]", "BAD_ARGS")
    if not isinstance(resolution, int) or not (4 <= resolution <= 128):
        return err_payload("resolution must be an integer 4–128", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "sdf_csg")

    node = {
        "id": node_id,
        "op": "sdf_csg",
        "primitives": primitives,
        "operations": operations,
        "bounds": [float(b) for b in bounds[:6]],
        "resolution": resolution,
        "isovalue": float(isovalue),
    }

    _, nid, err2 = append_feature_node(ctx, fid, node)
    if err2:
        return err_payload(err2, "ERROR")

    return ok_payload({
        "file_id": file_id,
        "id": nid or node_id,
        "op": "sdf_csg",
        "resolution": resolution,
        "num_primitives": len(primitives),
    })


# ── feature_uv_unwrap ─────────────────────────────────────────────────────────
#
# GK-P24: LSCM UV unwrap for mesh→SubD pipelines.

feature_uv_unwrap_spec = ToolSpec(
    name="feature_uv_unwrap",
    description=(
        "Append a `uv_unwrap` node to a `.feature` file. "
        "Computes an LSCM (Least-Squares Conformal Mapping) UV parametrization "
        "for a triangle mesh, minimising angle distortion (conformal energy). "
        "Well-suited for SubD cage UV sets where shape-preserving maps reduce "
        "texture swim. "
        "\n\n"
        "Supply a `mesh` (vertices + triangle faces) and optional `fixed_pins` "
        "(at least two non-coincident boundary vertex pins are required for a "
        "unique solution; if omitted, two boundary vertices are auto-selected). "
        "\n\n"
        "The resulting UV coordinates are stored in the node for downstream "
        "texture-mapping and toolpath-projection workflows. "
        "Pure-Python + NumPy (SciPy lsqr when available). No OCCT required."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "UUID of the target .feature file.",
            },
            "target_id": {
                "type": "string",
                "description": "Id of an existing mesh/SubD node to unwrap.",
            },
            "fixed_pins": {
                "type": "array",
                "description": (
                    "Optional: list of [vertex_index, u, v] pin triplets. "
                    "At least 2 non-coincident pins required for a unique solution. "
                    "Omit to use automatic boundary-vertex selection."
                ),
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                },
                "default": [],
            },
            "id": {"type": "string", "description": "Optional explicit node id."},
        },
        "required": ["file_id", "target_id"],
    },
)


@register(feature_uv_unwrap_spec, write=True)
async def run_feature_uv_unwrap(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    target_id = a.get("target_id", "").strip()
    fixed_pins = a.get("fixed_pins") or []
    node_id = a.get("id", "").strip()

    if not file_id or not target_id:
        return err_payload("file_id and target_id are required", "BAD_ARGS")
    if not isinstance(fixed_pins, list):
        return err_payload("fixed_pins must be an array", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "uv_unwrap")

    node = {
        "id": node_id,
        "op": "uv_unwrap",
        "target_id": target_id,
        "fixed_pins": fixed_pins,
    }

    _, nid, err2 = append_feature_node(ctx, fid, node)
    if err2:
        return err_payload(err2, "ERROR")

    return ok_payload({
        "file_id": file_id,
        "id": nid or node_id,
        "op": "uv_unwrap",
        "num_pins": len(fixed_pins),
    })


# ── feature_isotropic_remesh ──────────────────────────────────────────────────
#
# GK-P23: isotropic remesh (Botsch-Kobbelt 2004).

feature_isotropic_remesh_spec = ToolSpec(
    name="feature_isotropic_remesh",
    description=(
        "Append an `isotropic_remesh` node to a `.feature` file. "
        "Remeshes a triangle mesh toward a uniform target edge length using the "
        "Botsch-Kobbelt 2004 scheme: "
        "(1) split edges longer than 4/3 × L; "
        "(2) collapse edges shorter than 4/5 × L; "
        "(3) flip edges to improve valence toward 6; "
        "(4) tangential Laplacian smoothing. "
        "Boundary edges are never split or collapsed. "
        "Use as a pre-step before SubD retopology, UV unwrap, or FEA meshing. "
        "Pure-Python + NumPy fallback for when Instant Meshes is unavailable. "
        "No OCCT required."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "UUID of the target .feature file.",
            },
            "target_id": {
                "type": "string",
                "description": "Id of the mesh/SubD node to remesh.",
            },
            "target_edge_length": {
                "type": "number",
                "description": "Desired average edge length after remeshing (model units).",
                "exclusiveMinimum": 0,
            },
            "iterations": {
                "type": "integer",
                "description": "Number of split→collapse→flip→smooth cycles (default 5).",
                "minimum": 1,
                "maximum": 20,
                "default": 5,
            },
            "id": {"type": "string", "description": "Optional explicit node id."},
        },
        "required": ["file_id", "target_id", "target_edge_length"],
    },
)


@register(feature_isotropic_remesh_spec, write=True)
async def run_feature_isotropic_remesh(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    target_id = a.get("target_id", "").strip()
    target_edge_length = a.get("target_edge_length")
    iterations = a.get("iterations", 5)
    node_id = a.get("id", "").strip()

    if not file_id or not target_id:
        return err_payload("file_id and target_id are required", "BAD_ARGS")
    if target_edge_length is None or not isinstance(target_edge_length, (int, float)):
        return err_payload("target_edge_length is required and must be a number", "BAD_ARGS")
    if float(target_edge_length) <= 0:
        return err_payload("target_edge_length must be positive", "BAD_ARGS")
    if not isinstance(iterations, int) or not (1 <= iterations <= 20):
        return err_payload("iterations must be an integer 1–20", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "isotropic_remesh")

    node = {
        "id": node_id,
        "op": "isotropic_remesh",
        "target_id": target_id,
        "target_edge_length": float(target_edge_length),
        "iterations": iterations,
    }

    _, nid, err2 = append_feature_node(ctx, fid, node)
    if err2:
        return err_payload(err2, "ERROR")

    return ok_payload({
        "file_id": file_id,
        "id": nid or node_id,
        "op": "isotropic_remesh",
        "target_edge_length": float(target_edge_length),
        "iterations": iterations,
    })


# ── feature_retopo_snap ───────────────────────────────────────────────────────
#
# GK-P25: snap retopo cage to reference mesh surface.

feature_retopo_snap_spec = ToolSpec(
    name="feature_retopo_snap",
    description=(
        "Append a `retopo_snap` node to a `.feature` file. "
        "Projects each vertex of a retopology cage (SubD control cage) onto "
        "the nearest point on a reference source mesh, snapping the cage to "
        "the source surface. "
        "This is the surface-snap retopo backend: draw a coarse cage over a "
        "scan / high-res mesh, then snap it to conform tightly. "
        "The snap is purely positional (closest-point projection) — no normal "
        "alignment or tangential relaxation is applied. "
        "Requires NumPy. Pure-Python; no OCCT required."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "UUID of the target .feature file.",
            },
            "retopo_cage_id": {
                "type": "string",
                "description": "Id of the SubD cage node to snap.",
            },
            "source_mesh_id": {
                "type": "string",
                "description": (
                    "Id of the reference mesh/scan node to snap onto. "
                    "Must resolve to a mesh with vertices and faces."
                ),
            },
            "id": {"type": "string", "description": "Optional explicit node id."},
        },
        "required": ["file_id", "retopo_cage_id", "source_mesh_id"],
    },
)


@register(feature_retopo_snap_spec, write=True)
async def run_feature_retopo_snap(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    retopo_cage_id = a.get("retopo_cage_id", "").strip()
    source_mesh_id = a.get("source_mesh_id", "").strip()
    node_id = a.get("id", "").strip()

    if not file_id or not retopo_cage_id or not source_mesh_id:
        return err_payload(
            "file_id, retopo_cage_id, and source_mesh_id are required", "BAD_ARGS"
        )

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "retopo_snap")

    node = {
        "id": node_id,
        "op": "retopo_snap",
        "retopo_cage_id": retopo_cage_id,
        "source_mesh_id": source_mesh_id,
    }

    _, nid, err2 = append_feature_node(ctx, fid, node)
    if err2:
        return err_payload(err2, "ERROR")

    return ok_payload({
        "file_id": file_id,
        "id": nid or node_id,
        "op": "retopo_snap",
    })
