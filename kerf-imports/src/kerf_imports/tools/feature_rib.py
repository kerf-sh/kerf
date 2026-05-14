import json
import uuid
from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx
from tools.surfacing import next_node_id, read_feature_content, append_feature_node


def validate_rib_args(sketch_id, thickness_mm):
    if not sketch_id or not str(sketch_id).strip():
        return "sketch_id is required", "BAD_ARGS"
    if thickness_mm is None:
        return "thickness_mm is required", "BAD_ARGS"
    if not isinstance(thickness_mm, (int, float)) or thickness_mm <= 0:
        return "thickness_mm must be a positive number", "BAD_ARGS"
    return None, None


def build_rib_node(node_id, sketch_id, thickness_mm, both_sides, midplane, draft_angle_deg, name=""):
    node = {
        "id": node_id,
        "op": "rib",
        "params": {
            "sketch_id": sketch_id,
            "thickness_mm": thickness_mm,
            "both_sides": both_sides,
            "midplane": midplane,
            "draft_angle_deg": draft_angle_deg,
        },
    }
    if name:
        node["name"] = name
    return node


feature_rib_spec = ToolSpec(
    name="feature_rib",
    description=(
        "Append a `rib` node to a `.feature` file. "
        "Rib creates a parametric reinforcement wall by offsetting a closed sketch profile "
        "and sweeping it into a solid. "
        "When both_sides=true the profile is extruded symmetrically about the sketch plane; "
        "when midplane=true the extrusion is centered on the sketch plane; "
        "otherwise extrusion is outward from the sketch plane. "
        "draft_angle_deg applies a taper for mold release."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Target .feature file id."},
            "sketch_id": {"type": "string", "description": "Id of the closed-profile sketch to rib."},
            "thickness_mm": {"type": "number", "description": "Wall thickness in mm. Must be > 0."},
            "both_sides": {"type": "boolean", "description": "Extrude symmetrically about the sketch plane. Default false."},
            "midplane": {"type": "boolean", "description": "Center the extrusion on the sketch plane. Default false."},
            "draft_angle_deg": {"type": "number", "description": "Draft taper angle in degrees. Default 0."},
            "name": {"type": "string", "description": "Optional human-readable label for the node."},
        },
        "required": ["file_id", "sketch_id", "thickness_mm"],
    },
)


@register(feature_rib_spec, write=True)
async def run_feature_rib(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    sketch_id = a.get("sketch_id", "").strip()
    thickness_mm = a.get("thickness_mm")
    both_sides = bool(a.get("both_sides", False))
    midplane = bool(a.get("midplane", False))
    draft_angle_deg = float(a.get("draft_angle_deg", 0))
    name = a.get("name", "")

    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")

    err_msg, err_code = validate_rib_args(sketch_id, thickness_mm)
    if err_msg:
        return err_payload(err_msg, err_code)

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    node_id = next_node_id(content, "rib")
    node = build_rib_node(node_id, sketch_id, thickness_mm, both_sides, midplane, draft_angle_deg, name)

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id,
        "id": nid,
        "op": "rib",
    })