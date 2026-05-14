import json
import math
import uuid
from typing import Optional
from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx
from tools.surfacing import next_node_id, read_feature_content, append_feature_node


# ── Pure helper ───────────────────────────────────────────────────────────────

def helix_polyline(
    pitch: float,
    height: float,
    radius: float,
    direction: str = "right",
    cone_angle: float = 0.0,
    segments: int = 64,
) -> list[tuple[float, float, float]]:
    """Return a polyline approximation of a helix as a list of (x, y, z) tuples.

    Args:
        pitch:      Axial distance per full turn (mm).
        height:     Total axial height (mm).
        radius:     Coil radius at the base (mm). If cone_angle != 0 this is
                    the start radius; the end radius grows/shrinks accordingly.
        direction:  'right' (CCW from above, standard) or 'left' (CW).
        cone_angle: Half-angle in degrees. 0 → cylindrical.
        segments:   Number of line segments per turn. Total points = segments *
                    (height / pitch) + 1, rounded up.

    Returns:
        List of (x, y, z) tuples tracing the helix from z=0 to z=height.
    """
    if pitch <= 0 or height <= 0 or radius <= 0 or segments < 3:
        return []

    turns = height / pitch
    total_points = max(int(math.ceil(turns * segments)) + 1, 2)

    sign = -1.0 if direction == "left" else 1.0
    cone_rad = math.radians(cone_angle)
    pts: list[tuple[float, float, float]] = []

    for i in range(total_points):
        t = i / (total_points - 1)          # 0..1
        z = t * height
        angle = sign * 2.0 * math.pi * t * turns
        r = radius + z * math.tan(cone_rad)
        x = r * math.cos(angle)
        y = r * math.sin(angle)
        pts.append((x, y, z))

    return pts


# ── LLM tool spec ─────────────────────────────────────────────────────────────

feature_helix_spec = ToolSpec(
    name="feature_helix",
    description=(
        "Append a `helix` node to a `.feature` file. "
        "A helix sweeps a circular (or user-supplied) profile along a 3-D coil path. "
        "Use cases: springs, bolt threads, auger flights, worm gears."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "UUID of the target .feature file.",
            },
            "pitch_mm": {
                "type": "number",
                "description": "Axial distance between consecutive turns (mm). Must be > 0.",
            },
            "height_mm": {
                "type": "number",
                "description": "Total axial height of the helix (mm). Must be > 0.",
            },
            "radius_mm": {
                "type": "number",
                "description": "Coil radius (mm). For conical helices this is the base radius. Must be > 0.",
            },
            "direction": {
                "type": "string",
                "enum": ["right", "left"],
                "description": "'right' = CCW from above (standard thread direction). 'left' = CW. Default: 'right'.",
            },
            "cone_half_angle_deg": {
                "type": "number",
                "description": "Half-angle of the cone in degrees. 0 = cylindrical helix. Default: 0.",
            },
            "origin": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
                "description": "[x, y, z] base point of the helix. Default: [0, 0, 0].",
            },
            "axis": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
                "description": "Unit direction vector of the helix axis. Default: [0, 0, 1].",
            },
            "profile_sketch_id": {
                "type": "string",
                "description": "Optional UUID of a closed-profile sketch to sweep. Omit for default tiny circle.",
            },
            "name": {
                "type": "string",
                "description": "Human-readable label stored on the node.",
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id (e.g. 'helix-1'). Auto-generated if omitted.",
            },
        },
        "required": ["file_id", "pitch_mm", "height_mm", "radius_mm"],
    },
)


@register(feature_helix_spec, write=True)
async def run_feature_helix(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    # ── required params ──────────────────────────────────────────────────────
    file_id = a.get("file_id", "").strip()
    pitch_mm = a.get("pitch_mm")
    height_mm = a.get("height_mm")
    radius_mm = a.get("radius_mm")

    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")
    if pitch_mm is None or height_mm is None or radius_mm is None:
        return err_payload("pitch_mm, height_mm, and radius_mm are required", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a valid UUID", "BAD_ARGS")

    if not isinstance(pitch_mm, (int, float)) or pitch_mm <= 0:
        return err_payload("pitch_mm must be a positive number", "BAD_ARGS")
    if not isinstance(height_mm, (int, float)) or height_mm <= 0:
        return err_payload("height_mm must be a positive number", "BAD_ARGS")
    if not isinstance(radius_mm, (int, float)) or radius_mm <= 0:
        return err_payload("radius_mm must be a positive number", "BAD_ARGS")

    # ── optional params ──────────────────────────────────────────────────────
    direction = a.get("direction", "right")
    if direction not in ("right", "left"):
        return err_payload("direction must be 'right' or 'left'", "BAD_ARGS")

    cone_half_angle_deg = a.get("cone_half_angle_deg", 0.0)
    if not isinstance(cone_half_angle_deg, (int, float)) or cone_half_angle_deg < 0:
        return err_payload("cone_half_angle_deg must be >= 0", "BAD_ARGS")
    if cone_half_angle_deg >= 90:
        return err_payload("cone_half_angle_deg must be < 90", "BAD_ARGS")

    origin = a.get("origin", [0, 0, 0])
    if not isinstance(origin, list) or len(origin) != 3:
        return err_payload("origin must be [x, y, z]", "BAD_ARGS")

    axis = a.get("axis", [0, 0, 1])
    if not isinstance(axis, list) or len(axis) != 3:
        return err_payload("axis must be [x, y, z]", "BAD_ARGS")

    axis_len = math.sqrt(sum(v * v for v in axis))
    if axis_len < 1e-9:
        return err_payload("axis must be a non-zero vector", "BAD_ARGS")

    profile_sketch_id = a.get("profile_sketch_id", None)
    name = a.get("name", "").strip() or None
    node_id = a.get("id", "").strip()

    # ── read target file ─────────────────────────────────────────────────────
    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "helix")

    # ── build node ───────────────────────────────────────────────────────────
    node: dict = {
        "id": node_id,
        "op": "helix",
        "pitch_mm": float(pitch_mm),
        "height_mm": float(height_mm),
        "radius_mm": float(radius_mm),
        "direction": direction,
        "cone_half_angle_deg": float(cone_half_angle_deg),
        "origin": [float(v) for v in origin],
        "axis": [float(v) for v in axis],
    }
    if profile_sketch_id:
        node["profile_sketch_id"] = profile_sketch_id.strip()
    if name:
        node["name"] = name

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id,
        "id": nid,
        "op": "helix",
        "turns": float(height_mm) / float(pitch_mm),
    })
