import json
import uuid
from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx
from db.queries import files as file_queries


add_mate_spec = ToolSpec(
    name="add_mate",
    description="Add a geometric mate constraint to an assembly file. A mate connects two component entities (face/edge/vertex/axis) with a constraint type.",
    input_schema={
        "type": "object",
        "properties": {
            "assembly_file_id": {"type": "string"},
            "mate": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "type": {"type": "string", "enum": ["coincident", "concentric", "parallel", "perpendicular", "distance", "angle", "tangent"]},
                    "a": {
                        "type": "object",
                        "properties": {
                            "component_id": {"type": "string"},
                            "feature": {"type": "string", "enum": ["face", "edge", "vertex", "axis"]},
                            "feature_id": {"type": "string"},
                        },
                        "required": ["component_id", "feature", "feature_id"],
                    },
                    "b": {
                        "type": "object",
                        "properties": {
                            "component_id": {"type": "string"},
                            "feature": {"type": "string", "enum": ["face", "edge", "vertex", "axis"]},
                            "feature_id": {"type": "string"},
                        },
                        "required": ["component_id", "feature", "feature_id"],
                    },
                    "value": {"type": "number"},
                    "unit": {"type": "string"},
                    "tolerance_plus": {"type": "number"},
                    "tolerance_minus": {"type": "number"},
                    "flipped": {"type": "boolean"},
                },
                "required": ["type", "a", "b"],
            },
        },
        "required": ["assembly_file_id", "mate"],
    },
)

DIMENSIONAL_MATE_TYPES = {"distance", "angle"}
VALID_FEATURES = {"face", "edge", "vertex", "axis"}


def validate_mate(mate: dict) -> tuple[bool, str]:
    mate_type = mate.get("type", "")
    if not mate_type:
        return False, "mate type is required"

    if mate_type not in ("coincident", "concentric", "parallel", "perpendicular", "distance", "angle", "tangent"):
        return False, f"invalid mate type: {mate_type}"

    for ref_key in ("a", "b"):
        ref = mate.get(ref_key, {})
        if not ref:
            return False, f"mate {ref_key} is required"

        comp_id = ref.get("component_id", "")
        if not comp_id:
            return False, f"mate {ref_key}.component_id is required"

        feature = ref.get("feature", "")
        if feature not in VALID_FEATURES:
            return False, f"mate {ref_key}.feature must be one of: {', '.join(VALID_FEATURES)}"

        feature_id = ref.get("feature_id", "")
        if not feature_id:
            return False, f"mate {ref_key}.feature_id is required"

    if mate_type in DIMENSIONAL_MATE_TYPES:
        if "value" not in mate:
            return False, f"mate type '{mate_type}' requires value"
        if not mate.get("unit"):
            return False, f"mate type '{mate_type}' requires unit"

    return True, ""


def generate_mate_id(mate_type: str, existing_ids: set[str]) -> str:
    base = f"{mate_type}-mate"
    if base not in existing_ids:
        return base
    for i in range(1, 1000):
        candidate = f"{base}-{i}"
        if candidate not in existing_ids:
            return candidate
    return f"{base}-{uuid.uuid4().hex[:6]}"


@register(add_mate_spec, write=True)
async def run_add_mate(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    assembly_file_id = a.get("assembly_file_id", "").strip()
    if not assembly_file_id:
        return err_payload("assembly_file_id is required", "BAD_ARGS")

    try:
        fid = uuid.UUID(assembly_file_id)
    except Exception:
        return err_payload("assembly_file_id must be a uuid", "BAD_ARGS")

    mate = a.get("mate", {})
    valid, err_msg = validate_mate(mate)
    if not valid:
        return err_payload(err_msg, "BAD_MATE")

    row = await file_queries.get_file(ctx.pool, fid)
    if not row:
        return err_payload("assembly file not found", "NOT_FOUND")

    if row["kind"] != "assembly":
        return err_payload(f"file kind '{row['kind']}' is not an assembly", "BAD_KIND")

    content = row["content"] or "{}"
    try:
        doc = json.loads(content)
    except Exception:
        doc = {}

    if not isinstance(doc, dict):
        return err_payload("assembly file content is invalid JSON object", "BAD_FILE")

    existing_ids = set()
    for m in doc.get("mates", []):
        if isinstance(m, dict) and m.get("id"):
            existing_ids.add(m["id"])

    mate_id = mate.get("id", "")
    if not mate_id or mate_id in existing_ids:
        mate_id = generate_mate_id(mate.get("type", "coincident"), existing_ids)

    mate["id"] = mate_id

    if "mates" not in doc or not isinstance(doc["mates"], list):
        doc["mates"] = []
    doc["mates"].append(mate)

    new_content = json.dumps(doc, separators=(",", ":"))

    await file_queries.update_file(ctx.pool, fid, content=new_content)

    return ok_payload({
        "assembly_file_id": assembly_file_id,
        "mate_id": mate_id,
        "type": mate.get("type"),
    })


delete_mate_spec = ToolSpec(
    name="delete_mate",
    description="Remove a geometric mate constraint from an assembly file by its id.",
    input_schema={
        "type": "object",
        "properties": {
            "assembly_file_id": {"type": "string"},
            "mate_id": {"type": "string"},
        },
        "required": ["assembly_file_id", "mate_id"],
    },
)


@register(delete_mate_spec, write=True)
async def run_delete_mate(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    assembly_file_id = a.get("assembly_file_id", "").strip()
    mate_id = a.get("mate_id", "").strip()

    if not assembly_file_id or not mate_id:
        return err_payload("assembly_file_id and mate_id are required", "BAD_ARGS")

    try:
        fid = uuid.UUID(assembly_file_id)
    except Exception:
        return err_payload("assembly_file_id must be a uuid", "BAD_ARGS")

    row = await file_queries.get_file(ctx.pool, fid)
    if not row:
        return err_payload("assembly file not found", "NOT_FOUND")

    if row["kind"] != "assembly":
        return err_payload(f"file kind '{row['kind']}' is not an assembly", "BAD_KIND")

    content = row["content"] or "{}"
    try:
        doc = json.loads(content)
    except Exception:
        return err_payload("assembly file content is invalid JSON", "BAD_FILE")

    if not isinstance(doc, dict):
        return err_payload("assembly file content is invalid JSON object", "BAD_FILE")

    mates = doc.get("mates", [])
    if not isinstance(mates, list):
        return err_payload("mates is not a list", "BAD_FILE")

    found = False
    new_mates = []
    for m in mates:
        if isinstance(m, dict) and m.get("id") != mate_id:
            new_mates.append(m)
        else:
            found = True

    if not found:
        return err_payload(f"mate not found: {mate_id}", "NOT_FOUND")

    doc["mates"] = new_mates
    new_content = json.dumps(doc, separators=(",", ":"))

    await file_queries.update_file(ctx.pool, fid, content=new_content)

    return ok_payload({
        "assembly_file_id": assembly_file_id,
        "deleted_mate_id": mate_id,
    })


list_mates_spec = ToolSpec(
    name="list_mates",
    description="List all mate constraints in an assembly file.",
    input_schema={
        "type": "object",
        "properties": {"assembly_file_id": {"type": "string"}},
        "required": ["assembly_file_id"],
    },
)


@register(list_mates_spec)
async def run_list_mates(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    assembly_file_id = a.get("assembly_file_id", "").strip()
    if not assembly_file_id:
        return err_payload("assembly_file_id is required", "BAD_ARGS")

    try:
        fid = uuid.UUID(assembly_file_id)
    except Exception:
        return err_payload("assembly_file_id must be a uuid", "BAD_ARGS")

    row = await file_queries.get_file(ctx.pool, fid)
    if not row:
        return err_payload("assembly file not found", "NOT_FOUND")

    if row["kind"] != "assembly":
        return err_payload(f"file kind '{row['kind']}' is not an assembly", "BAD_KIND")

    content = row["content"] or "{}"
    try:
        doc = json.loads(content)
    except Exception:
        return err_payload("assembly file content is invalid JSON", "BAD_FILE")

    if not isinstance(doc, dict):
        return err_payload("assembly file content is invalid JSON object", "BAD_FILE")

    mates = doc.get("mates", [])
    if not isinstance(mates, list):
        mates = []

    return ok_payload({
        "assembly_file_id": assembly_file_id,
        "mates": mates,
        "count": len(mates),
    })


solve_assembly_spec = ToolSpec(
    name="solve_assembly",
    description="Solve the geometric constraints of an assembly using the SolveSpace solver. Computes component positions based on mates and returns solved transforms along with tolerance stack-up analysis.",
    input_schema={
        "type": "object",
        "properties": {
            "assembly_file_id": {"type": "string"},
            "fixed_component_id": {"type": "string"},
        },
        "required": ["assembly_file_id"],
    },
)


@register(solve_assembly_spec)
async def run_solve_assembly(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    assembly_file_id = a.get("assembly_file_id", "").strip()
    if not assembly_file_id:
        return err_payload("assembly_file_id is required", "BAD_ARGS")

    try:
        fid = uuid.UUID(assembly_file_id)
    except Exception:
        return err_payload("assembly_file_id must be a uuid", "BAD_ARGS")

    fixed_component_id = a.get("fixed_component_id", "").strip() or None

    row = await file_queries.get_file(ctx.pool, fid)
    if not row:
        return err_payload("assembly file not found", "NOT_FOUND")

    if row["kind"] != "assembly":
        return err_payload(f"file kind '{row['kind']}' is not an assembly", "BAD_KIND")

    content = row["content"] or "{}"
    try:
        doc = json.loads(content)
    except Exception:
        return err_payload("assembly file content is invalid JSON", "BAD_FILE")

    if not isinstance(doc, dict):
        return err_payload("assembly file content is invalid JSON object", "BAD_FILE")

    components = doc.get("components", [])
    mates = doc.get("mates", [])

    from tools.solvespace_wrapper import solve_assembly as solve

    result = solve(components, mates, fixed_component_id=fixed_component_id)

    return ok_payload({
        "assembly_file_id": assembly_file_id,
        "solved": result["solved"],
        "iterations": result["iterations"],
        "component_transforms": result["component_transforms"],
        "tolerance_stackup": result["tolerance_stackup"],
        "residuals": result["residuals"],
        "error": result["error"],
    })


assembly_add_external_component_spec = ToolSpec(
    name="assembly_add_external_component",
    description="Append a Component to an Assembly file whose geometry is sourced from a DIFFERENT project (cross-project reference). Use this when the user wants a mechanical assembly to reference a PCB from an electronics project.",
    input_schema={
        "type": "object",
        "properties": {
            "assembly_file_id": {"type": "string"},
            "external_project_id": {"type": "string"},
            "external_file_id": {"type": "string"},
            "kind": {"type": "string", "enum": ["board_3d", "board_outline_2d", "mesh"]},
            "pin": {"type": "string"},
            "component_id": {"type": "string"},
            "transform": {"type": "array", "items": {"type": "number"}},
        },
        "required": ["assembly_file_id", "external_project_id", "external_file_id", "kind"],
    },
)


@register(assembly_add_external_component_spec, write=True)
async def run_assembly_add_external_component(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    assembly_file_id = a.get("assembly_file_id", "").strip()
    external_project_id = a.get("external_project_id", "").strip()
    external_file_id = a.get("external_file_id", "").strip()
    kind = a.get("kind", "").strip()
    pin = a.get("pin", "").strip()
    component_id = a.get("component_id", "").strip()
    transform = a.get("transform", [])

    if not assembly_file_id or not external_project_id or not external_file_id or not kind:
        return err_payload("assembly_file_id, external_project_id, external_file_id, and kind are required", "BAD_ARGS")

    if kind not in ("board_3d", "board_outline_2d", "mesh"):
        return err_payload("kind must be one of board_3d / board_outline_2d / mesh", "BAD_ARGS")

    if not pin:
        pin = "tracking_latest"

    try:
        asm_fid = uuid.UUID(assembly_file_id)
    except Exception:
        return err_payload("assembly_file_id must be a uuid", "BAD_ARGS")

    try:
        ext_pid = uuid.UUID(external_project_id)
    except Exception:
        return err_payload("external_project_id must be a uuid", "BAD_ARGS")

    try:
        ext_fid = uuid.UUID(external_file_id)
    except Exception:
        return err_payload("external_file_id must be a uuid", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        "SELECT kind, content FROM files WHERE id = $1 AND project_id = $2 AND deleted_at IS NULL",
        asm_fid, ctx.project_id,
    )
    if not row:
        return err_payload("assembly file not found", "NOT_FOUND")

    if row["kind"] != "assembly":
        return err_payload(f"file kind {row['kind']} is not an assembly", "BAD_KIND")

    source_exists = await ctx.pool.fetchval(
        "SELECT EXISTS(SELECT 1 FROM files WHERE id = $1 AND project_id = $2 AND deleted_at IS NULL)",
        ext_fid, ext_pid,
    )
    if not source_exists:
        return err_payload("external_file_id not found in external_project_id", "NOT_FOUND")

    can_access = await ctx.pool.fetchval(
        """SELECT EXISTS(
            SELECT 1 FROM projects p
            JOIN workspace_members wm ON wm.workspace_id = p.workspace_id
            WHERE p.id = $1 AND wm.user_id = $2
        )""",
        ext_pid, ctx.user_id,
    )
    if not can_access:
        return err_payload("caller is not a member of the source project's workspace", "FORBIDDEN")

    content = row["content"] or "{}"
    try:
        doc = json.loads(content)
    except Exception:
        doc = {}

    if not isinstance(doc, dict):
        doc = {}

    raw_components = doc.get("components")
    if raw_components is None:
        raw_components = doc.get("children", [])

    if not isinstance(raw_components, list):
        raw_components = []

    used_ids = set()
    for item in raw_components:
        if isinstance(item, dict):
            if item.get("id"):
                used_ids.add(item["id"])

    base = component_id if component_id else f"ext-{external_file_id[:6]}"
    new_comp_id = base
    n = 1
    while new_comp_id in used_ids:
        n += 1
        new_comp_id = f"{base}-{n}"

    if len(transform) == 16:
        tf = transform
    else:
        tf = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]

    new_comp = {
        "id": new_comp_id,
        "file_id": "",
        "object_id": "",
        "transform": tf,
        "external_ref": {
            "project_id": external_project_id,
            "file_id": external_file_id,
            "kind": kind,
            "pin": pin,
        },
    }

    raw_components.append(new_comp)
    doc["components"] = raw_components
    if "children" in doc:
        del doc["children"]

    body = json.dumps(doc, indent="  ")

    await ctx.pool.execute(
        "UPDATE files SET content = $1, updated_at = now() WHERE id = $2 AND project_id = $3",
        body, asm_fid, ctx.project_id,
    )

    return ok_payload({
        "assembly_file_id": assembly_file_id,
        "component_id": new_comp_id,
        "external_project_id": external_project_id,
        "external_file_id": external_file_id,
        "kind": kind,
        "pin": pin,
    })


bulk_refresh_external_refs_spec = ToolSpec(
    name="bulk_refresh_external_refs",
    description="Refresh every cross-project external_ref in an assembly file by stamping last_seen_updated_at to each source file's current updated_at. Pinned-revision refs are skipped. Used by the assembly-level Update-all CTA.",
    input_schema={
        "type": "object",
        "properties": {
            "assembly_file_id": {"type": "string"},
        },
        "required": ["assembly_file_id"],
    },
)


@register(bulk_refresh_external_refs_spec, write=True)
async def run_bulk_refresh_external_refs(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    assembly_file_id = a.get("assembly_file_id", "").strip()
    if not assembly_file_id:
        return err_payload("assembly_file_id is required", "BAD_ARGS")

    try:
        asm_fid = uuid.UUID(assembly_file_id)
    except Exception:
        return err_payload("assembly_file_id must be a uuid", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        "SELECT kind, content FROM files WHERE id = $1 AND project_id = $2 AND deleted_at IS NULL",
        asm_fid, ctx.project_id,
    )
    if not row:
        return err_payload("assembly file not found", "NOT_FOUND")

    if row["kind"] != "assembly":
        return err_payload(f"file kind '{row['kind']}' is not an assembly", "BAD_KIND")

    content = row["content"] or "{}"
    try:
        doc = json.loads(content)
    except Exception:
        doc = {}

    if not isinstance(doc, dict):
        doc = {}

    raw_components = doc.get("components")
    if raw_components is None:
        raw_components = doc.get("children", [])

    if not isinstance(raw_components, list):
        raw_components = []

    refreshed = 0
    skipped_pinned = 0
    skipped_missing = 0

    for comp in raw_components:
        if not isinstance(comp, dict):
            continue
        ext_ref = comp.get("external_ref")
        if not isinstance(ext_ref, dict):
            continue
        project_id = ext_ref.get("project_id")
        file_id = ext_ref.get("file_id")
        if not project_id or not file_id:
            continue
        pin = ext_ref.get("pin", "tracking_latest")
        if pin != "tracking_latest":
            skipped_pinned += 1
            continue
        try:
            src_pid = uuid.UUID(project_id)
            src_fid = uuid.UUID(file_id)
        except Exception:
            skipped_missing += 1
            continue
        src_row = await ctx.pool.fetchrow(
            "SELECT updated_at FROM files WHERE id = $1 AND project_id = $2 AND deleted_at IS NULL",
            src_fid, src_pid,
        )
        if not src_row:
            skipped_missing += 1
            continue
        ext_ref["last_seen_updated_at"] = src_row["updated_at"].isoformat()
        refreshed += 1

    doc["components"] = raw_components
    if "children" in doc:
        del doc["children"]

    body = json.dumps(doc, indent="  ")

    await ctx.pool.execute(
        "UPDATE files SET content = $1, updated_at = now() WHERE id = $2 AND project_id = $3",
        body, asm_fid, ctx.project_id,
    )

    return ok_payload({
        "assembly_file_id": assembly_file_id,
        "refreshed": refreshed,
        "skipped_pinned": skipped_pinned,
        "skipped_missing": skipped_missing,
    })


lock_assembly_spec = ToolSpec(
    name="lock_assembly",
    description="Create or update a sibling .assembly.lock.json file capturing the current revision_id of every external_ref source. Acts like package-lock.json for cross-project assemblies — pins reproducible imports.",
    input_schema={
        "type": "object",
        "properties": {
            "assembly_file_id": {"type": "string"},
        },
        "required": ["assembly_file_id"],
    },
)


@register(lock_assembly_spec, write=True)
async def run_lock_assembly(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    assembly_file_id = a.get("assembly_file_id", "").strip()
    if not assembly_file_id:
        return err_payload("assembly_file_id is required", "BAD_ARGS")

    try:
        asm_fid = uuid.UUID(assembly_file_id)
    except Exception:
        return err_payload("assembly_file_id must be a uuid", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        "SELECT kind, content, name, parent_id FROM files WHERE id = $1 AND project_id = $2 AND deleted_at IS NULL",
        asm_fid, ctx.project_id,
    )
    if not row:
        return err_payload("assembly file not found", "NOT_FOUND")

    if row["kind"] != "assembly":
        return err_payload(f"file kind '{row['kind']}' is not an assembly", "BAD_KIND")

    content = row["content"] or "{}"
    try:
        doc = json.loads(content)
    except Exception:
        doc = {}

    if not isinstance(doc, dict):
        doc = {}

    raw_components = doc.get("components")
    if raw_components is None:
        raw_components = doc.get("children", [])

    if not isinstance(raw_components, list):
        raw_components = []

    entries = []
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()

    for comp in raw_components:
        if not isinstance(comp, dict):
            continue
        ext_ref = comp.get("external_ref")
        if not isinstance(ext_ref, dict):
            continue
        project_id = ext_ref.get("project_id")
        file_id = ext_ref.get("file_id")
        if not project_id or not file_id:
            continue
        kind = ext_ref.get("kind", "")
        component_id = comp.get("id", "")
        try:
            src_pid = uuid.UUID(project_id)
            src_fid = uuid.UUID(file_id)
        except Exception:
            continue
        rev_row = await ctx.pool.fetchrow(
            "SELECT id, created_at FROM file_revisions WHERE file_id = $1 AND project_id = $2 ORDER BY created_at DESC LIMIT 1",
            src_fid, src_pid,
        )
        if rev_row:
            revision_id = str(rev_row["id"])
        else:
            src_row = await ctx.pool.fetchrow(
                "SELECT updated_at FROM files WHERE id = $1 AND project_id = $2 AND deleted_at IS NULL",
                src_fid, src_pid,
            )
            if src_row:
                revision_id = src_row["updated_at"].isoformat()
            else:
                continue
        entries.append({
            "project_id": project_id,
            "file_id": file_id,
            "revision_id": revision_id,
            "kind": kind,
            "component_id": component_id,
        })

    lock_doc = {
        "version": 1,
        "generated_at": now_iso,
        "entries": entries,
    }

    asm_name = row["name"] or ""
    if asm_name.endswith(".assembly"):
        base_name = asm_name[:-8]
    else:
        base_name = asm_name
    lock_name = f"{base_name}.assembly.lock.json"

    lock_row = await ctx.pool.fetchrow(
        "SELECT id FROM files WHERE parent_id = $1 AND name = $2 AND deleted_at IS NULL",
        row["parent_id"], lock_name,
    )

    lock_body = json.dumps(lock_doc, indent="  ")

    if lock_row:
        lock_file_id = str(lock_row["id"])
        await ctx.pool.execute(
            "UPDATE files SET content = $1, updated_at = now() WHERE id = $2 AND project_id = $3",
            lock_body, uuid.UUID(lock_file_id), ctx.project_id,
        )
    else:
        new_lock_id = uuid.uuid4()
        await ctx.pool.execute(
            """INSERT INTO files (id, project_id, parent_id, name, kind, content, created_at, updated_at)
               VALUES ($1, $2, $3, $4, 'assembly_lock', $5, now(), now())""",
            new_lock_id, ctx.project_id, row["parent_id"], lock_name, lock_body,
        )
        lock_file_id = str(new_lock_id)

    return ok_payload({
        "assembly_file_id": assembly_file_id,
        "lock_file_id": lock_file_id,
        "entry_count": len(entries),
    })


unlock_assembly_spec = ToolSpec(
    name="unlock_assembly",
    description="Soft-delete the sibling .assembly.lock.json for an assembly — removes the dependency pinning so refs resolve to tracking_latest again.",
    input_schema={
        "type": "object",
        "properties": {
            "assembly_file_id": {"type": "string"},
        },
        "required": ["assembly_file_id"],
    },
)


@register(unlock_assembly_spec, write=True)
async def run_unlock_assembly(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    assembly_file_id = a.get("assembly_file_id", "").strip()
    if not assembly_file_id:
        return err_payload("assembly_file_id is required", "BAD_ARGS")

    try:
        asm_fid = uuid.UUID(assembly_file_id)
    except Exception:
        return err_payload("assembly_file_id must be a uuid", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        "SELECT kind, name, parent_id FROM files WHERE id = $1 AND project_id = $2 AND deleted_at IS NULL",
        asm_fid, ctx.project_id,
    )
    if not row:
        return err_payload("assembly file not found", "NOT_FOUND")

    if row["kind"] != "assembly":
        return err_payload(f"file kind '{row['kind']}' is not an assembly", "BAD_KIND")

    asm_name = row["name"] or ""
    if asm_name.endswith(".assembly"):
        base_name = asm_name[:-8]
    else:
        base_name = asm_name
    lock_name = f"{base_name}.assembly.lock.json"

    lock_row = await ctx.pool.fetchrow(
        "SELECT id FROM files WHERE parent_id = $1 AND name = $2 AND deleted_at IS NULL",
        row["parent_id"], lock_name,
    )

    if not lock_row:
        return ok_payload({
            "assembly_file_id": assembly_file_id,
            "unlocked": False,
            "reason": "no_lock_file",
        })

    lock_file_id = str(lock_row["id"])

    await ctx.pool.execute(
        "UPDATE files SET deleted_at = now() WHERE id = $1 AND project_id = $2",
        uuid.UUID(lock_file_id), ctx.project_id,
    )

    return ok_payload({
        "assembly_file_id": assembly_file_id,
        "lock_file_id": lock_file_id,
        "unlocked": True,
    })
