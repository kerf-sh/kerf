import json
import uuid
from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx
from tools.surfacing import next_node_id, read_feature_content, append_feature_node

VALID_MIRROR_PLANES = {"XY", "XZ", "YZ"}


def validate_mirror_args(source_feature_id, source_body_id, mirror_plane, mirror_face_id):
    """
    Validate feature_mirror arguments.
    Returns (error_msg, error_code) on failure, or (None, None) on success.
    """
    # Exactly one source required
    has_feature = bool(source_feature_id)
    has_body = bool(source_body_id)
    if has_feature and has_body:
        return "provide exactly one of source_feature_id or source_body_id, not both", "BAD_ARGS"
    if not has_feature and not has_body:
        return "one of source_feature_id or source_body_id is required", "BAD_ARGS"

    # Exactly one plane reference required
    has_plane = bool(mirror_plane)
    has_face = mirror_face_id is not None
    if has_plane and has_face:
        return "provide exactly one of mirror_plane or mirror_face_id, not both", "BAD_ARGS"
    if not has_plane and not has_face:
        return "one of mirror_plane or mirror_face_id is required", "BAD_ARGS"

    if has_plane:
        normalized = mirror_plane.upper() if isinstance(mirror_plane, str) else ""
        if normalized not in VALID_MIRROR_PLANES:
            return f"mirror_plane must be 'XY', 'XZ', or 'YZ', got '{mirror_plane}'", "BAD_ARGS"

    return None, None


def build_mirror_node(node_id, source_feature_id, source_body_id, mirror_plane, mirror_face_id, merge, name=""):
    """Build the feature node dict for a mirror_feature operation."""
    params = {"merge": merge}

    if source_feature_id:
        params["source_feature_id"] = source_feature_id
    else:
        params["source_body_id"] = source_body_id

    if mirror_plane:
        params["mirror_plane"] = mirror_plane.upper()
    else:
        params["mirror_face_id"] = mirror_face_id

    node = {
        "id": node_id,
        "op": "mirror_feature",
        "params": params,
    }
    if name:
        node["name"] = name
    return node


feature_mirror_spec = ToolSpec(
    name="feature_mirror",
    description=(
        "Append a `mirror_feature` node to a `.feature` file. "
        "Mirrors an existing feature node or an entire body about a world plane "
        "('XY', 'XZ', 'YZ') or a planar face id. "
        "When merge=true (default) the mirrored copy is boolean-unioned with the original. "
        "Exactly one of source_feature_id / source_body_id must be supplied; "
        "exactly one of mirror_plane / mirror_face_id must be supplied."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id.",
            },
            "source_feature_id": {
                "type": "string",
                "description": "Id of the feature node to mirror. Mutually exclusive with source_body_id.",
            },
            "source_body_id": {
                "type": "string",
                "description": "Id of the body to mirror. Mutually exclusive with source_feature_id.",
            },
            "mirror_plane": {
                "type": "string",
                "enum": ["XY", "XZ", "YZ"],
                "description": "World coordinate plane to mirror across. Mutually exclusive with mirror_face_id.",
            },
            "mirror_face_id": {
                "type": "integer",
                "description": "Post-evaluation face index to use as the mirror plane. Mutually exclusive with mirror_plane.",
            },
            "merge": {
                "type": "boolean",
                "description": "Boolean-union the mirror with the original. Default true.",
            },
            "name": {
                "type": "string",
                "description": "Optional human-readable label for the node.",
            },
        },
        "required": ["file_id"],
    },
)


@register(feature_mirror_spec, write=True)
async def run_feature_mirror(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    source_feature_id = a.get("source_feature_id", "").strip() if a.get("source_feature_id") else ""
    source_body_id = a.get("source_body_id", "").strip() if a.get("source_body_id") else ""
    mirror_plane = a.get("mirror_plane", "").strip() if a.get("mirror_plane") else ""
    mirror_face_id = a.get("mirror_face_id")  # may be None or int
    merge = a.get("merge", True)
    name = a.get("name", "")

    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")

    err_msg, err_code = validate_mirror_args(
        source_feature_id, source_body_id, mirror_plane, mirror_face_id
    )
    if err_msg:
        return err_payload(err_msg, err_code)

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    node_id = next_node_id(content, "mirror_feature")
    node = build_mirror_node(
        node_id, source_feature_id, source_body_id,
        mirror_plane, mirror_face_id, merge, name
    )

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id,
        "id": nid,
        "op": "mirror_feature",
    })
