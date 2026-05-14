import json
import uuid
from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx
from tools.file_ops import resolve_path


def _gen_id() -> str:
    return uuid.uuid4().hex[:8]


async def _load_sketch(ctx: ProjectCtx, path: str) -> tuple[dict, str]:
    rp = await resolve_path(ctx, path)
    if not rp.get("exists"):
        return {}, err_payload(f"file not found: {path}", "NOT_FOUND")

    row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE project_id = $1 AND path = $2 AND deleted_at IS NULL",
        ctx.project_id, path,
    )
    if not row:
        return {}, err_payload(f"file not found: {path}", "NOT_FOUND")

    try:
        sketch = json.loads(row["content"])
    except Exception as e:
        return {}, err_payload(f"invalid JSON: {e}", "BAD_CONTENT")
    return sketch, None


async def _save_sketch(ctx: ProjectCtx, path: str, sketch: dict) -> str:
    content = json.dumps(sketch, indent=2)
    await ctx.pool.execute(
        "UPDATE files SET content = $1, updated_at = now() WHERE project_id = $2 AND path = $3 AND deleted_at IS NULL",
        content, ctx.project_id, path,
    )
    return content


sketch_add_entity_spec = ToolSpec(
    name="sketch_add_entity",
    description="Add a geometric entity (point, line, circle, arc, ellipse, bspline) to a sketch file.",
    input_schema={
        "type": "object",
        "properties": {
            "file_path": {"type": "string"},
            "entity": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "type": {"type": "string"}},
                "required": ["type"],
            },
            "construction": {"type": "boolean"},
        },
        "required": ["file_path", "entity"],
    },
)


@register(sketch_add_entity_spec, write=True)
async def run_sketch_add_entity(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path = a.get("file_path", "")
    entity = a.get("entity", {})
    construction = a.get("construction", False)

    if not path:
        return err_payload("file_path is required", "BAD_ARGS")
    if not entity.get("type"):
        return err_payload("entity.type is required", "BAD_ARGS")

    sketch, err = await _load_sketch(ctx, path)
    if err:
        return err

    eid = entity.get("id")
    if not eid:
        eid = _gen_id()
        entity["id"] = eid

    if construction:
        entity["construction"] = True

    sketch.setdefault("entities", []).append(entity)
    await _save_sketch(ctx, path, sketch)
    return ok_payload({"ok": True, "id": eid})


sketch_add_constraint_spec = ToolSpec(
    name="sketch_add_constraint",
    description="Add a geometric or dimensional constraint to a sketch file.",
    input_schema={
        "type": "object",
        "properties": {
            "file_path": {"type": "string"},
            "constraint": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "type": {"type": "string"}},
                "required": ["type"],
            },
        },
        "required": ["file_path", "constraint"],
    },
)


@register(sketch_add_constraint_spec, write=True)
async def run_sketch_add_constraint(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path = a.get("file_path", "")
    constraint = a.get("constraint", {})

    if not path:
        return err_payload("file_path is required", "BAD_ARGS")
    if not constraint.get("type"):
        return err_payload("constraint.type is required", "BAD_ARGS")

    sketch, err = await _load_sketch(ctx, path)
    if err:
        return err

    cid = constraint.get("id")
    if not cid:
        cid = _gen_id()
        constraint["id"] = cid

    sketch.setdefault("constraints", []).append(constraint)
    await _save_sketch(ctx, path, sketch)
    return ok_payload({"ok": True, "id": cid})


sketch_set_constraint_value_spec = ToolSpec(
    name="sketch_set_constraint_value",
    description="Update the value of a dimensional constraint (distance/distance_x/distance_y/angle/radius/diameter).",
    input_schema={
        "type": "object",
        "properties": {
            "file_path": {"type": "string"},
            "constraint_id": {"type": "string"},
            "value": {"type": "number"},
        },
        "required": ["file_path", "constraint_id", "value"],
    },
)


@register(sketch_set_constraint_value_spec, write=True)
async def run_sketch_set_constraint_value(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path = a.get("file_path", "")
    constraint_id = a.get("constraint_id", "")
    value = a.get("value")

    if not path:
        return err_payload("file_path is required", "BAD_ARGS")
    if not constraint_id:
        return err_payload("constraint_id is required", "BAD_ARGS")
    if value is None:
        return err_payload("value is required", "BAD_ARGS")

    sketch, err = await _load_sketch(ctx, path)
    if err:
        return err

    constraints = sketch.get("constraints", [])
    found = False
    for c in constraints:
        if c.get("id") == constraint_id:
            c["value"] = value
            found = True
            break

    if not found:
        return err_payload(f"constraint not found: {constraint_id}", "NOT_FOUND")

    sketch["constraints"] = constraints
    await _save_sketch(ctx, path, sketch)
    return ok_payload({"ok": True})


sketch_delete_entity_spec = ToolSpec(
    name="sketch_delete_entity",
    description="Delete an entity by id, cascading to any line/arc/circle referencing a deleted point and any constraint referencing any deleted id.",
    input_schema={
        "type": "object",
        "properties": {
            "file_path": {"type": "string"},
            "entity_id": {"type": "string"},
        },
        "required": ["file_path", "entity_id"],
    },
)


@register(sketch_delete_entity_spec, write=True)
async def run_sketch_delete_entity(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path = a.get("file_path", "")
    entity_id = a.get("entity_id", "")

    if not path:
        return err_payload("file_path is required", "BAD_ARGS")
    if not entity_id:
        return err_payload("entity_id is required", "BAD_ARGS")

    sketch, err = await _load_sketch(ctx, path)
    if err:
        return err

    entities = sketch.get("entities", [])
    constraints = sketch.get("constraints", [])

    deleted_ids = set()
    to_delete = {entity_id}

    if entity_id not in [e.get("id") for e in entities]:
        return err_payload(f"entity not found: {entity_id}", "NOT_FOUND")

    while to_delete:
        current = to_delete.pop()
        if current in deleted_ids:
            continue
        deleted_ids.add(current)

        current_entity = next((e for e in entities if e.get("id") == current), None)
        if not current_entity:
            continue

        if current_entity.get("type") == "point":
            # Cascade: any edge that references this point must also be deleted.
            for ent in entities:
                if ent.get("id") in deleted_ids:
                    continue
                etype = ent.get("type")
                if etype == "line" and (ent.get("p1") == current or ent.get("p2") == current):
                    to_delete.add(ent["id"])
                elif etype == "arc" and (ent.get("center") == current or ent.get("start") == current or ent.get("end") == current):
                    to_delete.add(ent["id"])
                elif etype == "circle" and ent.get("center") == current:
                    to_delete.add(ent["id"])
                elif etype == "ellipse" and ent.get("center") == current:
                    to_delete.add(ent["id"])
                elif etype == "bspline" and current in ent.get("controls", []):
                    to_delete.add(ent["id"])

    sketch["entities"] = [e for e in entities if e.get("id") not in deleted_ids]
    sketch["constraints"] = [c for c in constraints if c.get("id") not in deleted_ids and not any(
        v in deleted_ids for v in c.values() if isinstance(v, str)
    )]

    await _save_sketch(ctx, path, sketch)
    return ok_payload({"ok": True, "deleted": list(deleted_ids)})