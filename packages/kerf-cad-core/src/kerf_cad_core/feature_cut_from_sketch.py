"""
feature_cut_from_sketch — subtract a sketched region from any planar face
of a target body, cutting normal to that face.

Unlike `pocket` (which cuts normal to the sketch plane), this tool orients the
sketch profile onto the target face's frame and extrudes the cutter along the
face's own normal.  Useful for cutting slots, notches, or pockets on inclined
or otherwise arbitrary planar faces without having to re-author the sketch on
that face.

OCCT pathway (evaluated in occtWorker.js → opCutFromSketch):
  1. faceById(prev, target_face_id)       → get the target face
  2. faceFrame(face)                      → origin + normal + uDir + vDir
  3. faceForSketchPath(sketch_path)       → build profile face on XY
  4. placeFaceOnPlane(profile, {type:'face', frame})
                                          → orient profile onto target face
  5. vec = -normal * depth  (or +normal when reverse=true)
  6. BRepPrimAPI_MakePrism(placed_profile, vec)  → cutter solid
  7. BRepAlgoAPI_Cut_3(prev, cutter)      → result

Face-id stability caveat:  target_face_id is the post-evaluation index
produced by the worker's face enumeration pass (same convention as push_pull).
If upstream nodes are structurally edited (e.g. the pad profile changes shape),
the worker may assign different indices and the stored face id may bind to the
wrong face.  Phase 4's persistent-naming layer will fix this; for now the LLM
doc instructs users to re-pick the face after structural upstream edits.
"""

from __future__ import annotations

import json
import uuid
from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx
from kerf_cad_core.surfacing import next_node_id, read_feature_content, append_feature_node


DEPTH_MIN = 1e-6


def validate_cut_from_sketch_args(
    target_face_id,
    sketch_path: str,
    depth,
    reverse: bool,
) -> tuple[str | None, str | None]:
    """
    Validate feature_cut_from_sketch arguments.
    Returns (error_msg, error_code) on failure, or (None, None) on success.
    """
    # target_face_id is required only when target_face_name is absent;
    # callers that supply target_face_name may pass None here.
    if target_face_id is not None and not isinstance(target_face_id, int):
        return "target_face_id must be an integer face index", "BAD_ARGS"
    if target_face_id is not None and target_face_id < 0:
        return "target_face_id must be >= 0", "BAD_ARGS"
    if not sketch_path or not isinstance(sketch_path, str) or not sketch_path.strip():
        return "sketch_path is required", "BAD_ARGS"
    if not isinstance(depth, (int, float)):
        return "depth must be a number", "BAD_ARGS"
    if depth <= 0:
        return f"depth must be > 0, got {depth}", "BAD_ARGS"
    if not isinstance(reverse, bool):
        return "reverse must be a boolean", "BAD_ARGS"
    return None, None


def build_cut_from_sketch_node(
    node_id: str,
    target_id: str,
    target_face_id: int | None,
    sketch_path: str,
    depth: float,
    reverse: bool,
    name: str = "",
    target_face_name: str = "",
) -> dict:
    """Build the feature node dict for a cut_from_sketch operation.

    Both target_face_name (persistent, primary) and target_face_id (legacy
    integer, fallback) are dual-written whenever either is available.
    """
    node: dict = {
        "id": node_id,
        "op": "cut_from_sketch",
        "target_id": target_id,
        "sketch_path": sketch_path,
        "depth": depth,
        "reverse": reverse,
    }
    # Dual-write: write target_face_name first (primary); keep target_face_id
    # for backward-compat fallback.  Either or both may be present.
    if target_face_name:
        node["target_face_name"] = target_face_name
    if target_face_id is not None:
        node["target_face_id"] = target_face_id
    if name:
        node["name"] = name
    return node


feature_cut_from_sketch_spec = ToolSpec(
    name="feature_cut_from_sketch",
    description=(
        "Append a `cut_from_sketch` node to a `.feature` file. "
        "Subtracts a sketched region from a specific planar face of the target body, "
        "extruding the cutter normal to that face rather than normal to the sketch plane. "
        "This lets you cut slots or pockets on inclined or side faces without "
        "reconstructing the sketch on that face. "
        "Supply target_face_name (persistent name from the worker's faceNames map, e.g. "
        "'Pad-A.TopCap') whenever available — it survives upstream topology changes. "
        "Also supply target_face_id (integer fallback) for backward compatibility. "
        "depth is the cut depth in mm (> 0). "
        "reverse=true flips the cut direction (extrude along +normal instead of -normal)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (UUID).",
            },
            "target_id": {
                "type": "string",
                "description": "Feature node id of the target body (e.g. 'pad-1').",
            },
            "target_face_name": {
                "type": "string",
                "description": (
                    "Persistent face name from the worker's faceNames map "
                    "(e.g. 'Pad-A.TopCap'). Primary resolver — survives upstream "
                    "topology changes. Supply alongside target_face_id."
                ),
            },
            "target_face_id": {
                "type": "integer",
                "description": (
                    "Post-evaluation face index of the target face (>= 0). "
                    "Legacy fallback when target_face_name is absent or stale."
                ),
            },
            "sketch_path": {
                "type": "string",
                "description": "Path to the .sketch file whose closed profile defines the cut region.",
            },
            "depth": {
                "type": "number",
                "description": "Cut depth in mm (must be > 0).",
            },
            "reverse": {
                "type": "boolean",
                "description": (
                    "When false (default) the cutter travels along -normal into the body. "
                    "When true it travels along +normal — use this when the face normal "
                    "points away from the body interior."
                ),
            },
            "name": {
                "type": "string",
                "description": "Optional human-readable label for the node.",
            },
        },
        "required": ["file_id", "target_id", "sketch_path", "depth"],
    },
)


@register(feature_cut_from_sketch_spec, write=True)
async def run_feature_cut_from_sketch(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    target_id = a.get("target_id", "").strip()
    target_face_id = a.get("target_face_id")
    target_face_name = a.get("target_face_name", "") or ""
    sketch_path = a.get("sketch_path", "").strip()
    depth = a.get("depth")
    reverse = a.get("reverse", False)
    name = a.get("name", "")

    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")
    if not target_id:
        return err_payload("target_id is required", "BAD_ARGS")
    if depth is None:
        return err_payload("depth is required", "BAD_ARGS")

    # Require at least one face reference.
    if not target_face_name and target_face_id is None:
        return err_payload(
            "provide target_face_name (persistent) and/or target_face_id (integer fallback)",
            "BAD_ARGS",
        )

    # Coerce reverse to bool in case the caller sent 0/1.
    if isinstance(reverse, int):
        reverse = bool(reverse)

    err_msg, err_code = validate_cut_from_sketch_args(
        target_face_id, sketch_path, depth, reverse
    )
    if err_msg:
        return err_payload(err_msg, err_code)

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a UUID", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    node_id = next_node_id(content, "cut")
    node = build_cut_from_sketch_node(
        node_id, target_id, target_face_id, sketch_path, float(depth), reverse, name,
        target_face_name=target_face_name,
    )

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id,
        "id": nid,
        "op": "cut_from_sketch",
    })
