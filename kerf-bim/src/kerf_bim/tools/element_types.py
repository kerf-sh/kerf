"""
element_types.py — LLM tools for type-level vs instance-level parameter management.

bulk_set_type_param   — change a type's default value; all instances inherit it
                          unless they have an instance-level override.
apply_type_to_instance — retarget an instance to a different type.
report_type_usage      — count how many instances use a given type across the project.
clone_type             — duplicate a type with a new id/name.
delete_type            — remove a type and optionally reassign its instances.
"""

import json
import uuid as _uuid

from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx
from tools.bim import resolve_path, record_revision_for_file


bulk_set_type_param_spec = ToolSpec(
    name="bulk_set_type_param",
    description=(
        "Set a type-level default for a param. All instances of this type will "
        "return the new value via resolveParams unless the instance has its own "
        "per-instance override. Operates on the .family.json file."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "family_file_id": {"type": "string"},
            "type_id": {"type": "string"},
            "param_name": {"type": "string"},
            "value": {},
        },
        "required": ["family_file_id", "type_id", "param_name", "value"],
    },
)


@register(bulk_set_type_param_spec, write=True)
async def run_bulk_set_type_param(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("family_file_id", "")
    type_id = a.get("type_id", "")
    param_name = a.get("param_name", "")
    value = a.get("value")

    try:
        fid = _uuid.UUID(file_id)
    except Exception:
        return err_payload("family_file_id must be a valid UUID", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE id = $1 AND project_id = $2 AND kind = 'family' AND deleted_at IS NULL",
        fid, ctx.project_id,
    )
    if not row:
        return err_payload("family file not found", "NOT_FOUND")

    try:
        doc = json.loads(row["content"])
    except Exception:
        return err_payload("family file content is not valid JSON", "PARSE_ERROR")

    type_obj = next((t for t in doc.get("types", []) if t.get("id") == type_id), None)
    if not type_obj:
        return err_payload(f"type \"{type_id}\" not found in family", "NOT_FOUND")

    param_def = next((p for p in doc.get("params", []) if p.get("name") == param_name), None)
    if not param_def:
        return err_payload(f"param \"{param_name}\" not defined in family", "NOT_FOUND")

    if param_def.get("type") == "number" and not isinstance(value, (int, float)):
        return err_payload(f"param \"{param_name}\" is number type", "TYPE_ERROR")
    if param_def.get("type") == "enum" and value not in param_def.get("options", []):
        return err_payload(f"value \"{value}\" not in enum options", "TYPE_ERROR")

    type_obj.setdefault("params", {})[param_name] = value
    body = json.dumps(doc, indent="  ")

    await ctx.pool.execute(
        "UPDATE files SET content = $1 WHERE id = $2 AND project_id = $3",
        body, fid, ctx.project_id,
    )
    await record_revision_for_file(ctx, fid, body, "tool")

    return ok_payload({"family_file_id": file_id, "type_id": type_id, "param_name": param_name, "value": value})


apply_type_to_instance_spec = ToolSpec(
    name="apply_type_to_instance",
    description=(
        "Switch an existing family instance to a different type. "
        "The instance keeps its per-instance overrides but adopts the new type's defaults."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "host_file_id": {"type": "string"},
            "instance_id": {"type": "string"},
            "type_id": {"type": "string"},
        },
        "required": ["host_file_id", "instance_id", "type_id"],
    },
)


@register(apply_type_to_instance_spec, write=True)
async def run_apply_type_to_instance(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    host_file_id = a.get("host_file_id", "")
    instance_id = a.get("instance_id", "")
    type_id = a.get("type_id", "")

    try:
        host_fid = _uuid.UUID(host_file_id)
    except Exception:
        return err_payload("host_file_id must be a valid UUID", "BAD_ARGS")

    host_row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE id = $1 AND project_id = $2 AND kind = 'bim' AND deleted_at IS NULL",
        host_fid, ctx.project_id,
    )
    if not host_row:
        return err_payload("host .bim file not found", "NOT_FOUND")

    try:
        bim_doc = json.loads(host_row["content"] or "{}")
    except Exception:
        return err_payload("host file content is not valid JSON", "PARSE_ERROR")

    instance = next((i for i in bim_doc.get("instances", []) if i.get("id") == instance_id), None)
    if not instance:
        return err_payload(f"instance \"{instance_id}\" not found", "NOT_FOUND")

    family_id = instance.get("family_id")
    if not family_id:
        return err_payload("instance has no family_id", "BAD_STATE")

    try:
        fam_fid = _uuid.UUID(family_id)
    except Exception:
        return err_payload("family_id is not a valid UUID", "BAD_STATE")

    fam_row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE id = $1 AND project_id = $2 AND kind = 'family' AND deleted_at IS NULL",
        fam_fid, ctx.project_id,
    )
    if not fam_row:
        return err_payload("family file not found", "NOT_FOUND")

    try:
        family_doc = json.loads(fam_row["content"])
    except Exception:
        return err_payload("family file content is not valid JSON", "PARSE_ERROR")

    type_obj = next((t for t in family_doc.get("types", []) if t.get("id") == type_id), None)
    if not type_obj:
        return err_payload(f"type \"{type_id}\" not found in family", "NOT_FOUND")

    instance["type_id"] = type_id
    body = json.dumps(bim_doc, indent="  ")

    await ctx.pool.execute(
        "UPDATE files SET content = $1 WHERE id = $2 AND project_id = $3",
        body, host_fid, ctx.project_id,
    )
    await record_revision_for_file(ctx, host_fid, body, "tool")

    return ok_payload({"instance_id": instance_id, "type_id": type_id, "host_file_id": host_file_id})


report_type_usage_spec = ToolSpec(
    name="report_type_usage",
    description=(
        "Scan all .bim files in the project for instances referencing a given type. "
        "Returns counts grouped by host file."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "family_file_id": {"type": "string"},
            "type_id": {"type": "string"},
        },
        "required": ["family_file_id", "type_id"],
    },
)


@register(report_type_usage_spec, write=False)
async def run_report_type_usage(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("family_file_id", "")
    type_id = a.get("type_id", "")

    try:
        fid = _uuid.UUID(file_id)
    except Exception:
        return err_payload("family_file_id must be a valid UUID", "BAD_ARGS")

    fam_row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE id = $1 AND project_id = $2 AND kind = 'family' AND deleted_at IS NULL",
        fid, ctx.project_id,
    )
    if not fam_row:
        return err_payload("family file not found", "NOT_FOUND")

    bim_rows = await ctx.pool.fetch(
        "SELECT id, content FROM files WHERE project_id = $1 AND kind = 'bim' AND deleted_at IS NULL",
        ctx.project_id,
    )

    usage = []
    total = 0
    for row in bim_rows:
        try:
            bim_doc = json.loads(row["content"] or "{}")
        except Exception:
            continue
        count = sum(
            1 for i in bim_doc.get("instances", [])
            if i.get("family_id") == file_id and i.get("type_id") == type_id
        )
        if count:
            usage.append({"host_file_id": str(row["id"]), "count": count})
            total += count

    return ok_payload({"family_file_id": file_id, "type_id": type_id, "total": total, "by_host": usage})


clone_type_spec = ToolSpec(
    name="clone_type",
    description="Duplicate an existing type with a new id and name. The original type is unchanged.",
    input_schema={
        "type": "object",
        "properties": {
            "family_file_id": {"type": "string"},
            "source_type_id": {"type": "string"},
            "new_name": {"type": "string"},
        },
        "required": ["family_file_id", "source_type_id", "new_name"],
    },
)


@register(clone_type_spec, write=True)
async def run_clone_type(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("family_file_id", "")
    source_type_id = a.get("source_type_id", "")
    new_name = a.get("new_name", "")

    try:
        fid = _uuid.UUID(file_id)
    except Exception:
        return err_payload("family_file_id must be a valid UUID", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE id = $1 AND project_id = $2 AND kind = 'family' AND deleted_at IS NULL",
        fid, ctx.project_id,
    )
    if not row:
        return err_payload("family file not found", "NOT_FOUND")

    try:
        doc = json.loads(row["content"])
    except Exception:
        return err_payload("family file content is not valid JSON", "PARSE_ERROR")

    source_type = next((t for t in doc.get("types", []) if t.get("id") == source_type_id), None)
    if not source_type:
        return err_payload(f"source type \"{source_type_id}\" not found", "NOT_FOUND")

    new_type_id = f"type-{_uuid.uuid4().hex[:8]}"
    new_type = {
        "id": new_type_id,
        "name": new_name,
        "params": {**source_type.get("params", {})},
    }
    doc.setdefault("types", []).append(new_type)
    body = json.dumps(doc, indent="  ")

    await ctx.pool.execute(
        "UPDATE files SET content = $1 WHERE id = $2 AND project_id = $3",
        body, fid, ctx.project_id,
    )
    await record_revision_for_file(ctx, fid, body, "tool")

    return ok_payload({"family_file_id": file_id, "new_type": new_type})


delete_type_spec = ToolSpec(
    name="delete_type",
    description=(
        "Remove a type from a family. If reassign_to is provided, all instances "
        "in every .bim file that use this type are moved to reassign_to. "
        "Otherwise instances retain their type_id but the type definition is gone "
        "(they will resolve defaults only)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "family_file_id": {"type": "string"},
            "type_id": {"type": "string"},
            "reassign_to": {"type": "string"},
        },
        "required": ["family_file_id", "type_id"],
    },
)


@register(delete_type_spec, write=True)
async def run_delete_type(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("family_file_id", "")
    type_id = a.get("type_id", "")
    reassign_to = a.get("reassign_to")

    try:
        fid = _uuid.UUID(file_id)
    except Exception:
        return err_payload("family_file_id must be a valid UUID", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE id = $1 AND project_id = $2 AND kind = 'family' AND deleted_at IS NULL",
        fid, ctx.project_id,
    )
    if not row:
        return err_payload("family file not found", "NOT_FOUND")

    try:
        doc = json.loads(row["content"])
    except Exception:
        return err_payload("family file content is not valid JSON", "PARSE_ERROR")

    type_idx = next((i for i, t in enumerate(doc.get("types", [])) if t.get("id") == type_id), None)
    if type_idx is None:
        return err_payload(f"type \"{type_id}\" not found in family", "NOT_FOUND")

    if reassign_to:
        reassign_type = next((t for t in doc.get("types", []) if t.get("id") == reassign_to), None)
        if not reassign_type:
            return err_payload(f"reassign_to type \"{reassign_to}\" not found", "NOT_FOUND")

    doc["types"].pop(type_idx)
    family_body = json.dumps(doc, indent="  ")

    await ctx.pool.execute(
        "UPDATE files SET content = $1 WHERE id = $2 AND project_id = $3",
        family_body, fid, ctx.project_id,
    )
    await record_revision_for_file(ctx, fid, family_body, "tool")

    if reassign_to:
        bim_rows = await ctx.pool.fetch(
            "SELECT id, content FROM files WHERE project_id = $1 AND kind = 'bim' AND deleted_at IS NULL",
            ctx.project_id,
        )
        reassign_count = 0
        for row in bim_rows:
            try:
                bim_doc = json.loads(row["content"] or "{}")
            except Exception:
                continue
            changed = False
            for inst in bim_doc.get("instances", []):
                if inst.get("family_id") == file_id and inst.get("type_id") == type_id:
                    inst["type_id"] = reassign_to
                    changed = True
                    reassign_count += 1
            if changed:
                bim_body = json.dumps(bim_doc, indent="  ")
                await ctx.pool.execute(
                    "UPDATE files SET content = $1 WHERE id = $2 AND project_id = $3",
                    bim_body, row["id"], ctx.project_id,
                )
                await record_revision_for_file(ctx, row["id"], bim_body, "tool")

        return ok_payload({
            "family_file_id": file_id,
            "deleted_type_id": type_id,
            "reassigned_to": reassign_to,
            "reassigned_instance_count": reassign_count,
        })

    return ok_payload({"family_file_id": file_id, "deleted_type_id": type_id, "reassigned_to": None})