import json
import uuid
from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx
from kerf_api.tools.file_ops import resolve_path


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


# ---------------------------------------------------------------------------
# Carbon-copy tool

sketch_carbon_copy_spec = ToolSpec(
    name="sketch_carbon_copy",
    description=(
        "Copy entities from a source sketch into a target sketch as driven reference geometry "
        "(is_reference: true). Reference entities participate in constraints but are not extruded. "
        "Optionally filter by entity_ids and/or apply a translation + rotation."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "source_file_path": {"type": "string", "description": "Path to the source .sketch file."},
            "target_file_path": {"type": "string", "description": "Path to the target .sketch file."},
            "entity_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional subset of edge entity ids to copy (default: all edges).",
            },
            "translation": {
                "type": "object",
                "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
                "description": "Optional translation applied to copied coordinates.",
            },
            "rotation_deg": {
                "type": "number",
                "description": "Optional rotation in degrees applied to copied coordinates.",
            },
        },
        "required": ["source_file_path", "target_file_path"],
    },
)


@register(sketch_carbon_copy_spec, write=True)
async def run_sketch_carbon_copy(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    src_path = a.get("source_file_path", "")
    tgt_path = a.get("target_file_path", "")
    entity_ids = a.get("entity_ids")  # None means all
    translation = a.get("translation") or {}
    rotation_deg = a.get("rotation_deg")

    if not src_path:
        return err_payload("source_file_path is required", "BAD_ARGS")
    if not tgt_path:
        return err_payload("target_file_path is required", "BAD_ARGS")

    src_sketch, err = await _load_sketch(ctx, src_path)
    if err:
        return err
    tgt_sketch, err = await _load_sketch(ctx, tgt_path)
    if err:
        return err

    # Derive a stable cc_source id from the source path.
    src_id = src_path.replace("/", "_").replace(".", "_").strip("_")
    edge_types = {"line", "circle", "arc"}

    src_entities = src_sketch.get("entities", [])
    src_by_id = {e["id"]: e for e in src_entities}

    # Filter to requested entity ids (edges only).
    to_copy = [e for e in src_entities if e.get("type") in edge_types and not e.get("is_reference")]
    if entity_ids is not None:
        id_set = set(entity_ids)
        to_copy = [e for e in to_copy if e.get("id") in id_set]

    import math
    tx = translation.get("x", 0)
    ty = translation.get("y", 0)
    rad = math.radians(rotation_deg or 0)
    cos_r = math.cos(rad)
    sin_r = math.sin(rad)

    def transform_pt(x, y):
        rx = x * cos_r - y * sin_r + tx
        ry = x * sin_r + y * cos_r + ty
        return rx, ry

    prefix = src_id + "_"

    def transform_ent(ent):
        """Return a list of new entities (aux points + edge) for a single source edge."""
        results = []
        eid = lambda raw: f"{prefix}{raw}"

        def add_point(pid):
            src_pt = src_by_id.get(pid)
            if not src_pt:
                return
            nx, ny = transform_pt(src_pt.get("x", 0), src_pt.get("y", 0))
            results.append({
                "id": eid(pid), "type": "point", "x": nx, "y": ny,
                "is_reference": True, "source_id": pid, "cc_source": src_id, "construction": True,
            })

        t = ent.get("type")
        if t == "line":
            add_point(ent["p1"])
            add_point(ent["p2"])
            results.append({
                "id": eid(ent["id"]), "type": "line",
                "p1": eid(ent["p1"]), "p2": eid(ent["p2"]),
                "is_reference": True, "source_id": ent["id"], "cc_source": src_id, "construction": True,
            })
        elif t == "circle":
            add_point(ent["center"])
            results.append({
                "id": eid(ent["id"]), "type": "circle",
                "center": eid(ent["center"]), "radius": ent.get("radius", 0),
                "is_reference": True, "source_id": ent["id"], "cc_source": src_id, "construction": True,
            })
        elif t == "arc":
            add_point(ent["center"])
            add_point(ent["start"])
            add_point(ent["end"])
            results.append({
                "id": eid(ent["id"]), "type": "arc",
                "center": eid(ent["center"]),
                "start": eid(ent["start"]),
                "end": eid(ent["end"]),
                "sweep_ccw": ent.get("sweep_ccw", True),
                "is_reference": True, "source_id": ent["id"], "cc_source": src_id, "construction": True,
            })
        return results

    new_ents = []
    seen_ids = set()
    for ent in to_copy:
        for ne in transform_ent(ent):
            if ne["id"] not in seen_ids:
                seen_ids.add(ne["id"])
                new_ents.append(ne)

    # Remove old reference entities for this source, then append new ones.
    existing = [e for e in tgt_sketch.get("entities", []) if not (e.get("is_reference") and e.get("cc_source") == src_id)]
    tgt_sketch["entities"] = existing + new_ents

    prev_sources = tgt_sketch.get("cc_sources", [])
    if src_id not in prev_sources:
        prev_sources = prev_sources + [src_id]
    tgt_sketch["cc_sources"] = prev_sources

    await _save_sketch(ctx, tgt_path, tgt_sketch)
    return ok_payload({"ok": True, "copied": len([e for e in new_ents if e["type"] != "point"]), "cc_source": src_id})


# ---------------------------------------------------------------------------
# Sketch validation tool

sketch_validate_spec = ToolSpec(
    name="sketch_validate",
    description=(
        "Validate a sketch for common issues: open contours, self-intersections, "
        "redundant/over-constraints, dangling endpoints, and unresolved external references. "
        "Returns {errors, warnings} each as a list of {kind, severity, message, entity_id?}."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Path to the .sketch file to validate."},
        },
        "required": ["file_path"],
    },
)


@register(sketch_validate_spec)
async def run_sketch_validate(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path = a.get("file_path", "")
    if not path:
        return err_payload("file_path is required", "BAD_ARGS")

    sketch, err = await _load_sketch(ctx, path)
    if err:
        return err

    errors = []
    warnings = []

    entities = sketch.get("entities", [])
    constraints = sketch.get("constraints", [])

    # --- open_contour ---
    edges = [e for e in entities if not e.get("construction") and not e.get("is_reference") and e.get("type") in ("line", "arc")]
    if edges:
        from collections import Counter
        ep_count = Counter()
        for e in edges:
            if e["type"] == "line":
                ep_count[e["p1"]] += 1
                ep_count[e["p2"]] += 1
            elif e["type"] == "arc":
                ep_count[e["start"]] += 1
                ep_count[e["end"]] += 1
        for pid, count in ep_count.items():
            if count % 2 != 0:
                errors.append({
                    "kind": "open_contour", "severity": "error",
                    "message": f"Open contour: endpoint \"{pid}\" is not connected to another edge.",
                    "entity_id": pid,
                })

    # --- self_intersection (line vs line only for Python backend; JS does full check) ---
    import math as _math
    pts_map = {e["id"]: e for e in entities if e.get("type") == "point"}

    def seg_intersect(a1, a2, b1, b2):
        """Return True if segments a1-a2 and b1-b2 properly intersect."""
        def cross(u, v): return u[0] * v[1] - u[1] * v[0]
        r = (a2[0] - a1[0], a2[1] - a1[1])
        s = (b2[0] - b1[0], b2[1] - b1[1])
        denom = cross(r, s)
        if abs(denom) < 1e-9:
            return False
        d = (b1[0] - a1[0], b1[1] - a1[1])
        t = cross(d, s) / denom
        u = cross(d, r) / denom
        return 1e-7 < t < 1 - 1e-7 and 1e-7 < u < 1 - 1e-7

    line_ents = [e for e in entities if e.get("type") == "line" and not e.get("is_reference") and not e.get("construction")]
    for i in range(len(line_ents)):
        for j in range(i + 1, len(line_ents)):
            eA, eB = line_ents[i], line_ents[j]
            # Adjacent edges share a point — skip.
            if eA.get("p1") in (eB.get("p1"), eB.get("p2")) or eA.get("p2") in (eB.get("p1"), eB.get("p2")):
                continue
            p1A = pts_map.get(eA.get("p1"))
            p2A = pts_map.get(eA.get("p2"))
            p1B = pts_map.get(eB.get("p1"))
            p2B = pts_map.get(eB.get("p2"))
            if not all([p1A, p2A, p1B, p2B]):
                continue
            if seg_intersect(
                (p1A.get("x", 0), p1A.get("y", 0)),
                (p2A.get("x", 0), p2A.get("y", 0)),
                (p1B.get("x", 0), p1B.get("y", 0)),
                (p2B.get("x", 0), p2B.get("y", 0)),
            ):
                errors.append({
                    "kind": "self_intersection", "severity": "error",
                    "message": f"Self-intersection between \"{eA['id']}\" and \"{eB['id']}\".",
                    "entity_id": eA["id"],
                })

    # --- redundant_constraint ---
    dof = 0
    has_origin = False
    for e in entities:
        if e.get("is_reference"):
            continue
        if e.get("type") == "point":
            dof += 2
            if e.get("id") == "origin":
                has_origin = True
        elif e.get("type") == "circle":
            dof += 1
        elif e.get("type") == "arc":
            dof += 3
    if has_origin:
        dof -= 2
    constraint_dof_map = {
        "coincident": 2, "symmetric": 2, "midpoint": 2, "fixed": 2,
        "horizontal": 1, "vertical": 1, "parallel": 1, "perpendicular": 1,
        "tangent": 1, "equal_length": 1, "equal_radius": 1,
        "distance": 1, "distance_x": 1, "distance_y": 1,
        "angle": 1, "radius": 1, "diameter": 1,
        "point_on_line": 1, "point_on_arc": 1, "point_on_circle": 1,
    }
    for c in constraints:
        ct = c.get("type", "")
        if ct == "block":
            dof -= len(c.get("refs", [])) * 2
        else:
            dof -= constraint_dof_map.get(ct, 0)
    if dof < 0:
        errors.append({
            "kind": "redundant_constraint", "severity": "error",
            "message": f"Sketch is over-constrained (estimated DOF = {dof}). Remove {abs(dof)} constraint(s).",
        })

    # --- dangling_endpoint ---
    anchored = set()
    for c in constraints:
        if c.get("type") == "coincident":
            if c.get("a"):
                anchored.add(c["a"])
            if c.get("b"):
                anchored.add(c["b"])
        if c.get("type") == "fixed" and c.get("point"):
            anchored.add(c["point"])
        if c.get("type") == "block":
            for r in c.get("refs", []):
                anchored.add(r)
    edge_pts = set()
    for e in entities:
        if e.get("is_reference") or e.get("construction"):
            continue
        if e.get("type") == "line":
            edge_pts.add(e.get("p1"))
            edge_pts.add(e.get("p2"))
        if e.get("type") == "arc":
            edge_pts.add(e.get("start"))
            edge_pts.add(e.get("end"))
    for pid in edge_pts:
        if pid and pid != "origin" and pid not in anchored:
            warnings.append({
                "kind": "dangling_endpoint", "severity": "warning",
                "message": f"Endpoint \"{pid}\" has no coincident or fixed constraint.",
                "entity_id": pid,
            })

    # --- unresolved_external_ref ---
    for e in entities:
        if not e.get("is_reference"):
            continue
        if e.get("unresolved"):
            errors.append({
                "kind": "unresolved_external_ref", "severity": "error",
                "message": f"Reference entity \"{e['id']}\" has an unresolved source.",
                "entity_id": e["id"],
            })

    return ok_payload({"errors": errors, "warnings": warnings})