import json
import uuid
from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx
from tools.surfacing import next_node_id, read_feature_content, append_feature_node

MAX_TRANSFORMS = 4
VALID_LINEAR_DIRECTIONS = {"x", "y", "z"}
VALID_POLAR_AXES = {"x", "y", "z"}
VALID_MIRROR_PLANES = {"XY", "XZ", "YZ"}


def validate_transforms(transforms):
    if not isinstance(transforms, list) or len(transforms) == 0:
        return "transforms must be a non-empty list", "BAD_ARGS"
    if len(transforms) > MAX_TRANSFORMS:
        return f"transforms exceeds maximum of {MAX_TRANSFORMS}", "BAD_ARGS"

    for i, t in enumerate(transforms):
        if not isinstance(t, dict):
            return f"transform[{i}] must be an object", "BAD_ARGS"
        kind = t.get("kind", "").lower()
        if kind == "linear":
            direction = t.get("direction", "").lower()
            count = t.get("count")
            spacing = t.get("spacing")
            if direction not in VALID_LINEAR_DIRECTIONS:
                return f"transform[{i}].direction must be 'x', 'y', or 'z', got '{direction}'", "BAD_ARGS"
            if not isinstance(count, int) or count < 2:
                return f"transform[{i}].count must be an integer >= 2, got '{count}'", "BAD_ARGS"
            if not isinstance(spacing, (int, float)) or spacing <= 0:
                return f"transform[{i}].spacing must be a positive number, got '{spacing}'", "BAD_ARGS"
        elif kind == "polar":
            axis = t.get("axis", "").lower()
            count = t.get("count")
            total_angle_deg = t.get("total_angle_deg")
            if axis not in VALID_POLAR_AXES:
                return f"transform[{i}].axis must be 'x', 'y', or 'z', got '{axis}'", "BAD_ARGS"
            if not isinstance(count, int) or count < 2:
                return f"transform[{i}].count must be an integer >= 2, got '{count}'", "BAD_ARGS"
            if not isinstance(total_angle_deg, (int, float)) or total_angle_deg <= 0 or total_angle_deg > 360:
                return f"transform[{i}].total_angle_deg must be between 0 and 360, got '{total_angle_deg}'", "BAD_ARGS"
        elif kind == "mirror":
            plane = t.get("plane_or_face", "")
            if not plane:
                return f"transform[{i}].plane_or_face is required for mirror transform", "BAD_ARGS"
        else:
            return f"transform[{i}].kind must be 'linear', 'polar', or 'mirror', got '{kind}'", "BAD_ARGS"
    return None, None


def validate_multi_transform_args(source_feature_id, transforms):
    if not source_feature_id or not isinstance(source_feature_id, str):
        return "source_feature_id is required and must be a string", "BAD_ARGS"
    return validate_transforms(transforms)


def build_multi_transform_node(node_id, source_feature_id, transforms, name=""):
    node = {
        "id": node_id,
        "op": "multi_transform",
        "params": {
            "source_feature_id": source_feature_id,
            "transforms": transforms,
        },
    }
    if name:
        node["name"] = name
    return node


feature_multi_transform_spec = ToolSpec(
    name="feature_multi_transform",
    description=(
        "Append a `multi_transform` node to a `.feature` file. "
        "Composes multiple pattern operations (linear, polar, mirror) on an existing feature. "
        "Transforms are applied in order; the result is the cartesian product of all transform instances. "
        "Maximum 4 nested transforms supported."
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
                "description": "Id of the source feature to transform.",
            },
            "transforms": {
                "type": "array",
                "description": "Array of transform operations (max 4). Each transform has 'kind' and kind-specific params.",
                "items": {
                    "type": "object",
                    "properties": {
                        "kind": {
                            "type": "string",
                            "enum": ["linear", "polar", "mirror"],
                            "description": "Type of transform.",
                        },
                        "direction": {
                            "type": "string",
                            "enum": ["x", "y", "z"],
                            "description": "Direction for linear transform.",
                        },
                        "count": {
                            "type": "integer",
                            "description": "Number of copies for linear/polar transform (>= 2).",
                        },
                        "spacing": {
                            "type": "number",
                            "description": "Spacing between copies for linear transform (> 0).",
                        },
                        "axis": {
                            "type": "string",
                            "enum": ["x", "y", "z"],
                            "description": "Axis for polar transform.",
                        },
                        "total_angle_deg": {
                            "type": "number",
                            "description": "Total sweep angle for polar transform (0 < angle <= 360).",
                        },
                        "plane_or_face": {
                            "type": "string",
                            "description": "Plane ('XY','XZ','YZ') or face id for mirror transform.",
                        },
                    },
                    "required": ["kind"],
                    "allOf": [
                        {
                            "if": {"properties": {"kind": {"const": "linear"}}},
                            "then": {"required": ["direction", "count", "spacing"]},
                        },
                        {
                            "if": {"properties": {"kind": {"const": "polar"}}},
                            "then": {"required": ["axis", "count", "total_angle_deg"]},
                        },
                        {
                            "if": {"properties": {"kind": {"const": "mirror"}}},
                            "then": {"required": ["plane_or_face"]},
                        },
                    ],
                },
            },
            "name": {
                "type": "string",
                "description": "Optional human-readable label for the node.",
            },
        },
        "required": ["file_id", "source_feature_id", "transforms"],
    },
)


@register(feature_multi_transform_spec, write=True)
async def run_feature_multi_transform(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    source_feature_id = a.get("source_feature_id", "").strip()
    transforms = a.get("transforms", [])
    name = a.get("name", "")

    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")

    err_msg, err_code = validate_multi_transform_args(source_feature_id, transforms)
    if err_msg:
        return err_payload(err_msg, err_code)

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    doc = json.loads(content) if content else {"version": 1, "features": []}
    feature_ids = {f.get("id") for f in doc.get("features", []) if isinstance(f, dict)}
    if source_feature_id not in feature_ids:
        return err_payload(f"source_feature_id '{source_feature_id}' not found in feature tree", "NOT_FOUND")

    node_id = next_node_id(content, "multi_transform")
    node = build_multi_transform_node(node_id, source_feature_id, transforms, name)

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id,
        "id": nid,
        "op": "multi_transform",
    })