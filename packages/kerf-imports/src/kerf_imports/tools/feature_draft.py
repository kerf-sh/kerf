import json
import uuid
from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx
from tools.surfacing import next_node_id, read_feature_content, append_feature_node

ANGLE_MIN = -30.0
ANGLE_MAX = 30.0
VALID_PULL_DIRECTIONS = {"inward", "outward"}


def validate_draft_args(face_ids, neutral_plane_face_id, angle_deg, pull_direction):
    """
    Validate feature_draft arguments.
    Returns (error_msg, error_code) on failure, or (None, None) on success.
    """
    if not face_ids or not isinstance(face_ids, list) or len(face_ids) == 0:
        return "face_ids must be a non-empty list", "BAD_ARGS"
    if neutral_plane_face_id is None:
        return "neutral_plane_face_id is required", "BAD_ARGS"
    if not isinstance(angle_deg, (int, float)):
        return "angle_deg must be a number", "BAD_ARGS"
    if angle_deg < ANGLE_MIN or angle_deg > ANGLE_MAX:
        return f"angle_deg must be between {ANGLE_MIN} and {ANGLE_MAX}, got {angle_deg}", "BAD_ARGS"
    if pull_direction not in VALID_PULL_DIRECTIONS:
        return f"pull_direction must be 'inward' or 'outward', got '{pull_direction}'", "BAD_ARGS"
    return None, None


def build_draft_node(node_id, face_ids, neutral_plane_face_id, angle_deg, pull_direction, name=""):
    """Build the feature node dict for a draft operation."""
    node = {
        "id": node_id,
        "op": "draft",
        "params": {
            "face_ids": face_ids,
            "neutral_plane_face_id": neutral_plane_face_id,
            "angle_deg": angle_deg,
            "pull_direction": pull_direction,
        },
    }
    if name:
        node["name"] = name
    return node


feature_draft_spec = ToolSpec(
    name="feature_draft",
    description=(
        "Append a `draft` node to a `.feature` file. "
        "Draft applies a taper angle to a set of faces relative to a neutral plane — "
        "the standard operation for injection-molded parts to enable mold release. "
        "angle_deg is clamped to [-30, 30]. "
        "pull_direction 'outward' widens the faces away from the mold axis; "
        "'inward' tapers them toward it."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id.",
            },
            "face_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Post-evaluation face indices to be drafted (at least one required).",
            },
            "neutral_plane_face_id": {
                "type": "integer",
                "description": "Face id of the neutral plane (typically the parting-line face).",
            },
            "angle_deg": {
                "type": "number",
                "description": "Draft angle in degrees. Must be within [-30, 30].",
            },
            "pull_direction": {
                "type": "string",
                "enum": ["inward", "outward"],
                "description": "Direction of taper relative to the neutral plane. Default 'outward'.",
            },
            "name": {
                "type": "string",
                "description": "Optional human-readable label for the node.",
            },
        },
        "required": ["file_id", "face_ids", "neutral_plane_face_id", "angle_deg"],
    },
)


@register(feature_draft_spec, write=True)
async def run_feature_draft(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    face_ids = a.get("face_ids", [])
    neutral_plane_face_id = a.get("neutral_plane_face_id")
    angle_deg = a.get("angle_deg")
    pull_direction = a.get("pull_direction", "outward")
    name = a.get("name", "")

    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")

    if angle_deg is None:
        return err_payload("angle_deg is required", "BAD_ARGS")

    err_msg, err_code = validate_draft_args(face_ids, neutral_plane_face_id, angle_deg, pull_direction)
    if err_msg:
        return err_payload(err_msg, err_code)

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    node_id = next_node_id(content, "draft")
    node = build_draft_node(node_id, face_ids, neutral_plane_face_id, angle_deg, pull_direction, name)

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id,
        "id": nid,
        "op": "draft",
    })
