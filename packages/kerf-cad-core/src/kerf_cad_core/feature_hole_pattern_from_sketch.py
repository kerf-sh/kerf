"""
feature_hole_pattern_from_sketch — FreeCAD-parity shortcut: N cylinder cuts
driven by point entities in a sketch.

Appends a single ``hole_pattern`` feature node to a ``.feature`` JSON file.
The OCCT worker (``opHolePattern``) evaluates the node at render time:

1. Parse the sketch at ``sketch_path`` and collect all ``type:'point'``
   entities (excluding the implicit origin point).
2. For each point ``(x, y)`` call ``cutCylinderAtPoint`` — the shared helper
   factored out of ``opHole`` — to punch a cylinder of ``diameter × depth``
   through the running body.
3. Non-point entities (lines, arcs, circles) in the sketch are silently
   ignored so the user can mix in construction geometry as visual guides.

This op is **parametric**: editing the points sketch and re-triggering
evaluation re-runs all N cuts automatically.  No N hand-written ``hole`` nodes
needed.

Schema emitted:

.. code-block:: json

    {
      "id": "hole_pattern-1",
      "op": "hole_pattern",
      "target_id": "pad-1",
      "sketch_path": "/hole-grid.sketch",
      "diameter": 3.0,
      "depth": 8.0
    }

``target_id`` is optional in the JSON (the worker operates on whatever shape
is current in the timeline).  ``countersink_diameter`` and
``countersink_depth`` are reserved for a future patch; do not populate them
in v1.
"""

from __future__ import annotations

import json
import uuid

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx
from kerf_cad_core.surfacing import next_node_id, read_feature_content, append_feature_node


DIAMETER_MIN = 1e-6
DEPTH_MIN = 1e-6


# ── Pure validation helper ────────────────────────────────────────────────────

def validate_hole_pattern_args(
    sketch_path: object,
    diameter: object,
    depth: object,
) -> tuple[str | None, str | None]:
    """Validate args; return (error_msg, error_code) or (None, None) on success."""
    if not sketch_path or not isinstance(sketch_path, str) or not sketch_path.strip():
        return "sketch_path is required and must be a non-empty string", "BAD_ARGS"
    if not sketch_path.endswith(".sketch"):
        return "sketch_path must end in '.sketch'", "BAD_ARGS"
    if not isinstance(diameter, (int, float)):
        return "diameter must be a number", "BAD_ARGS"
    if diameter <= 0:
        return f"diameter must be > 0, got {diameter}", "BAD_ARGS"
    if not isinstance(depth, (int, float)):
        return "depth must be a number", "BAD_ARGS"
    if depth <= 0:
        return f"depth must be > 0, got {depth}", "BAD_ARGS"
    return None, None


def extract_sketch_points(sketch_json: object) -> list[dict]:
    """
    Return a list of ``{'x': float, 'y': float}`` dicts for every
    ``type='point'`` entity in a parsed sketch, excluding the implicit
    origin sentinel (``id == 'origin'``).

    ``sketch_json`` may be a JSON string, a dict, or ``None``.
    Non-point entities are silently skipped (construction geometry is
    allowed alongside the hole-centre points).

    Returns an empty list when the sketch is absent or has no eligible points.
    """
    if sketch_json is None:
        return []
    try:
        obj = sketch_json if isinstance(sketch_json, dict) else json.loads(sketch_json)
    except Exception:
        return []
    entities = obj.get("entities", []) if isinstance(obj, dict) else []
    points = []
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        if ent.get("type") != "point":
            continue
        if ent.get("id") == "origin":
            continue
        try:
            points.append({"x": float(ent.get("x", 0)), "y": float(ent.get("y", 0))})
        except (TypeError, ValueError):
            continue
    return points


def build_hole_pattern_node(
    node_id: str,
    sketch_path: str,
    diameter: float,
    depth: float,
    target_id: str = "",
    name: str = "",
) -> dict:
    """Return the feature-node dict for a hole_pattern operation."""
    node: dict = {
        "id": node_id,
        "op": "hole_pattern",
        "sketch_path": sketch_path,
        "diameter": float(diameter),
        "depth": float(depth),
    }
    if target_id:
        node["target_id"] = target_id
    if name:
        node["name"] = name
    return node


# ── LLM tool spec ─────────────────────────────────────────────────────────────

feature_hole_pattern_from_sketch_spec = ToolSpec(
    name="feature_hole_pattern_from_sketch",
    description=(
        "Append a `hole_pattern` node to a `.feature` file. "
        "FreeCAD-parity shortcut: reads every `type:'point'` entity in a "
        "sketch and cuts one cylinder (diameter × depth) per point through "
        "the target body. Parametric — editing the sketch and re-evaluating "
        "automatically updates all holes. "
        "Non-point sketch entities (lines, arcs, circles) are silently "
        "ignored, so you can mix construction geometry into the same sketch "
        "as visual guides. "
        "OCCT path: for each point (x,y) in the sketch, "
        "cutCylinderAtPoint(body, x, y, diameter, depth) is called in "
        "sequence — same primitive as `hole`. "
        "If the sketch has no point entities the worker raises an error; "
        "ensure the sketch contains at least one `type:'point'` entity. "
        "Use `sketch_add_entity` with `type:'point'` to add hole centres "
        "to the sketch before calling this tool."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "UUID of the target .feature file.",
            },
            "sketch_path": {
                "type": "string",
                "description": (
                    "Absolute path of the points-bearing .sketch file "
                    "(e.g. '/hole-grid.sketch'). "
                    "Must contain at least one `type:'point'` entity."
                ),
            },
            "diameter": {
                "type": "number",
                "description": "Hole diameter in mm. Must be > 0.",
            },
            "depth": {
                "type": "number",
                "description": "Hole depth in mm. Must be > 0.",
            },
            "target_id": {
                "type": "string",
                "description": (
                    "Optional feature-node id of the body to cut into "
                    "(e.g. 'pad-1'). When omitted the worker cuts into "
                    "whichever shape is current in the timeline."
                ),
            },
            "name": {
                "type": "string",
                "description": "Optional human-readable label for the feature node.",
            },
            "id": {
                "type": "string",
                "description": (
                    "Optional explicit node id (e.g. 'hpat-1'). "
                    "Auto-generated if omitted."
                ),
            },
        },
        "required": ["file_id", "sketch_path", "diameter", "depth"],
    },
)


@register(feature_hole_pattern_from_sketch_spec, write=True)
async def run_feature_hole_pattern_from_sketch(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    # ── required params ──────────────────────────────────────────────────────
    file_id = a.get("file_id", "").strip()
    sketch_path = a.get("sketch_path", "").strip()
    diameter = a.get("diameter")
    depth = a.get("depth")

    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")
    if diameter is None:
        return err_payload("diameter is required", "BAD_ARGS")
    if depth is None:
        return err_payload("depth is required", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a valid UUID", "BAD_ARGS")

    # ── optional params with defaults ────────────────────────────────────────
    target_id = a.get("target_id", "").strip() or ""
    name = a.get("name", "").strip() or ""
    node_id = a.get("id", "").strip()

    # ── validate ─────────────────────────────────────────────────────────────
    err_msg, err_code = validate_hole_pattern_args(sketch_path, diameter, depth)
    if err_msg:
        return err_payload(err_msg, err_code)

    # ── read target file ─────────────────────────────────────────────────────
    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "hole_pattern")

    # ── build and append node ─────────────────────────────────────────────────
    node = build_hole_pattern_node(
        node_id, sketch_path, diameter, depth, target_id, name,
    )

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id,
        "id": nid,
        "op": "hole_pattern",
    })
