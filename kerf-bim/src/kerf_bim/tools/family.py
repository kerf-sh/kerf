"""
family.py — LLM tools for the .family.json parametric component system.

A family is a reusable parametric template (window, door, column, …).
Families live as files with kind='family' inside the project tree.
Instances live inside .bim files and reference a family by its file id.
"""

import json
import uuid as _uuid

from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx

# Re-use file/folder helpers from the bim module without importing the whole module
# (avoids triggering bim-specific side-effects; we only need low-level DB helpers)
from tools.bim import ensure_folders, record_revision_for_file, resolve_path

# ── constants ──────────────────────────────────────────────────────────────────

VALID_CATEGORIES = {
    'Wall', 'Floor', 'Roof', 'Door', 'Window', 'Column', 'Beam',
    'Stair', 'Railing', 'Ceiling', 'Furniture', 'Generic',
}

VALID_PARAM_TYPES = {'number', 'string', 'boolean', 'enum'}


# ── pure helpers ───────────────────────────────────────────────────────────────

def _validate_param(p: dict, index: int) -> list[str]:
    errors = []
    prefix = f"params[{index}]"
    if not isinstance(p.get('name'), str) or not p['name']:
        errors.append(f"{prefix}: name is required")
    if p.get('type') not in VALID_PARAM_TYPES:
        errors.append(f"{prefix}: type must be one of {sorted(VALID_PARAM_TYPES)}")
    if p.get('type') == 'enum':
        opts = p.get('options', [])
        if not isinstance(opts, list) or len(opts) == 0:
            errors.append(f"{prefix}: enum params require a non-empty options list")
        elif 'default' in p and p['default'] not in opts:
            errors.append(f"{prefix}: default \"{p['default']}\" is not in options")
    if p.get('type') == 'number':
        mn, mx = p.get('min'), p.get('max')
        if mn is not None and mx is not None and mn > mx:
            errors.append(f"{prefix}: min ({mn}) must be <= max ({mx})")
        if 'default' in p and not isinstance(p['default'], (int, float)):
            errors.append(f"{prefix}: default must be a number for number params")
    return errors


def validate_family_doc(doc: dict) -> list[str]:
    errors = []
    if doc.get('version') != 1:
        errors.append("version must be 1")
    if not isinstance(doc.get('name'), str):
        errors.append("name must be a string")
    if doc.get('category') not in VALID_CATEGORIES:
        errors.append(f"category must be one of {sorted(VALID_CATEGORIES)}")
    params = doc.get('params', [])
    if not isinstance(params, list):
        errors.append("params must be an array")
    else:
        seen = set()
        for i, p in enumerate(params):
            errors.extend(_validate_param(p, i))
            name = p.get('name')
            if name:
                if name in seen:
                    errors.append(f"params[{i}]: duplicate param name \"{name}\"")
                seen.add(name)
    return errors


def resolve_params(family_doc: dict, instance: dict) -> dict:
    """Merge: defaults → type params → instance params."""
    resolved = {}
    for p in family_doc.get('params', []):
        if 'default' in p:
            resolved[p['name']] = p['default']

    type_id = instance.get('type_id')
    if type_id:
        for t in family_doc.get('types', []):
            if t.get('id') == type_id:
                resolved.update(t.get('params', {}))
                break

    if isinstance(instance.get('params'), dict):
        resolved.update(instance['params'])

    return resolved


# ── create_family ──────────────────────────────────────────────────────────────

create_family_spec = ToolSpec(
    name="create_family",
    description=(
        "Create a new .family.json parametric component template. "
        "category must be one of: Wall, Floor, Roof, Door, Window, Column, Beam, "
        "Stair, Railing, Ceiling, Furniture, Generic. "
        "Each param needs at minimum {name, type}; number params accept min/max; "
        "enum params require an options list."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute path, must end with .family.json"},
            "name": {"type": "string"},
            "category": {"type": "string"},
            "params": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "type": {"type": "string"},
                        "unit": {"type": "string"},
                        "default": {},
                        "options": {"type": "array"},
                        "min": {"type": "number"},
                        "max": {"type": "number"},
                    },
                    "required": ["name", "type"],
                },
            },
        },
        "required": ["path", "name", "category"],
    },
)


@register(create_family_spec, write=True)
async def run_create_family(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path = a.get("path", "")
    name = a.get("name", "")
    category = a.get("category", "")
    params = a.get("params", [])

    clean = path.rstrip("/")
    if not clean.startswith("/"):
        return err_payload("path must be absolute", "BAD_ARGS")
    if not clean.endswith(".family.json"):
        return err_payload("path must end with .family.json", "BAD_KIND")

    rp = await resolve_path(ctx, clean)
    if rp.get("exists"):
        return err_payload("path already exists", "EXISTS")

    doc = {
        "version": 1,
        "name": name,
        "category": category,
        "params": params,
        "types": [],
        "host_rules": {"allowed_hosts": [], "host_alignment": "centered_on_face"},
        "representation": None,
    }

    errs = validate_family_doc(doc)
    if errs:
        return err_payload("; ".join(errs), "VALIDATION_ERROR")

    body = json.dumps(doc, indent="  ")

    parts = [p for p in clean.strip("/").split("/") if p]
    parent_id = await ensure_folders(ctx, parts[:-1])
    leaf = parts[-1]

    new_id = await ctx.pool.fetchval(
        "INSERT INTO files(project_id, parent_id, name, kind, content) VALUES ($1, $2, $3, 'family', $4) RETURNING id",
        ctx.project_id, parent_id, leaf, body,
    )
    await record_revision_for_file(ctx, new_id, body, "tool")

    return ok_payload({"path": clean, "id": str(new_id)})


# ── add_family_param ───────────────────────────────────────────────────────────

add_family_param_spec = ToolSpec(
    name="add_family_param",
    description="Add a parameter definition to an existing .family.json file.",
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
            "name": {"type": "string"},
            "type": {"type": "string"},
            "unit": {"type": "string"},
            "default": {},
            "options": {"type": "array"},
            "min": {"type": "number"},
            "max": {"type": "number"},
        },
        "required": ["file_id", "name", "type"],
    },
)


@register(add_family_param_spec, write=True)
async def run_add_family_param(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "")
    param_name = a.get("name", "")
    param_type = a.get("type", "")

    try:
        fid = _uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a valid UUID", "BAD_ARGS")

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

    if any(p.get("name") == param_name for p in doc.get("params", [])):
        return err_payload(f"param \"{param_name}\" already exists", "EXISTS")

    new_param = {"name": param_name, "type": param_type}
    for key in ("unit", "default", "options", "min", "max"):
        if key in a:
            new_param[key] = a[key]

    param_errors = _validate_param(new_param, len(doc.get("params", [])))
    if param_errors:
        return err_payload("; ".join(param_errors), "VALIDATION_ERROR")

    doc.setdefault("params", []).append(new_param)
    body = json.dumps(doc, indent="  ")

    await ctx.pool.execute(
        "UPDATE files SET content = $1 WHERE id = $2 AND project_id = $3",
        body, fid, ctx.project_id,
    )
    await record_revision_for_file(ctx, fid, body, "tool")

    return ok_payload({"file_id": file_id, "param": new_param})


# ── add_family_type ────────────────────────────────────────────────────────────

add_family_type_spec = ToolSpec(
    name="add_family_type",
    description=(
        "Add a named parameter preset (type) to a .family.json file. "
        "A type is a saved set of param values; instances can reference it via type_id."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
            "id": {"type": "string", "description": "Unique id for this type, e.g. 'type-600x900'"},
            "name": {"type": "string"},
            "params": {"type": "object"},
        },
        "required": ["file_id", "id", "name"],
    },
)


@register(add_family_type_spec, write=True)
async def run_add_family_type(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "")
    type_id = a.get("id", "")
    type_name = a.get("name", "")
    type_params = a.get("params", {})

    try:
        fid = _uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a valid UUID", "BAD_ARGS")

    if not type_id:
        return err_payload("id is required", "BAD_ARGS")

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

    doc.setdefault("types", [])
    if any(t.get("id") == type_id for t in doc["types"]):
        return err_payload(f"type \"{type_id}\" already exists", "EXISTS")

    new_type = {"id": type_id, "name": type_name, "params": type_params or {}}
    doc["types"].append(new_type)
    body = json.dumps(doc, indent="  ")

    await ctx.pool.execute(
        "UPDATE files SET content = $1 WHERE id = $2 AND project_id = $3",
        body, fid, ctx.project_id,
    )
    await record_revision_for_file(ctx, fid, body, "tool")

    return ok_payload({"file_id": file_id, "type": new_type})


# ── instantiate_family ─────────────────────────────────────────────────────────

instantiate_family_spec = ToolSpec(
    name="instantiate_family",
    description=(
        "Append an instance record to a .bim file. The instance references a family "
        "by its file_id and optionally a type_id and per-instance param overrides."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "family_file_id": {"type": "string"},
            "host_file_id": {"type": "string", "description": "UUID of the .bim file"},
            "host_ref": {"type": "string", "description": "e.g. wall element id"},
            "type_id": {"type": "string"},
            "params": {"type": "object"},
        },
        "required": ["family_file_id", "host_file_id"],
    },
)


@register(instantiate_family_spec, write=True)
async def run_instantiate_family(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    family_file_id = a.get("family_file_id", "")
    host_file_id = a.get("host_file_id", "")

    try:
        fam_fid = _uuid.UUID(family_file_id)
    except Exception:
        return err_payload("family_file_id must be a valid UUID", "BAD_ARGS")

    try:
        host_fid = _uuid.UUID(host_file_id)
    except Exception:
        return err_payload("host_file_id must be a valid UUID", "BAD_ARGS")

    # Verify family exists
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

    # Verify bim host exists
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

    # Validate instance params against family
    instance = {k: v for k, v in a.items() if k not in ("family_file_id", "host_file_id")}
    resolved = resolve_params(family_doc, instance)

    param_defs = {p["name"]: p for p in family_doc.get("params", [])}
    param_errors = []
    for pname, value in resolved.items():
        defn = param_defs.get(pname)
        if not defn:
            continue
        if defn.get("type") == "number":
            mn, mx = defn.get("min"), defn.get("max")
            if mn is not None and value < mn:
                param_errors.append(f"param \"{pname}\": {value} is below min {mn}")
            if mx is not None and value > mx:
                param_errors.append(f"param \"{pname}\": {value} is above max {mx}")
        if defn.get("type") == "enum":
            if value not in defn.get("options", []):
                param_errors.append(f"param \"{pname}\": \"{value}\" is not a valid option")

    if param_errors:
        return err_payload("; ".join(param_errors), "VALIDATION_ERROR")

    instance_id = str(_uuid.uuid4())
    instance_record = {
        "id": instance_id,
        "type": "instance",
        "family_id": family_file_id,
    }
    if a.get("type_id"):
        instance_record["type_id"] = a["type_id"]
    if a.get("host_ref"):
        instance_record["host_ref"] = a["host_ref"]
    if a.get("params"):
        instance_record["params"] = a["params"]

    bim_doc.setdefault("instances", []).append(instance_record)
    body = json.dumps(bim_doc, indent="  ")

    await ctx.pool.execute(
        "UPDATE files SET content = $1 WHERE id = $2 AND project_id = $3",
        body, host_fid, ctx.project_id,
    )
    await record_revision_for_file(ctx, host_fid, body, "tool")

    return ok_payload({"instance_id": instance_id, "host_file_id": host_file_id})


# ── update_instance ────────────────────────────────────────────────────────────

update_instance_spec = ToolSpec(
    name="update_instance",
    description="Update per-instance param overrides for an existing family instance in a .bim file.",
    input_schema={
        "type": "object",
        "properties": {
            "host_file_id": {"type": "string"},
            "instance_id": {"type": "string"},
            "params": {"type": "object"},
        },
        "required": ["host_file_id", "instance_id", "params"],
    },
)


@register(update_instance_spec, write=True)
async def run_update_instance(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    host_file_id = a.get("host_file_id", "")
    instance_id = a.get("instance_id", "")
    new_params = a.get("params", {})

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

    instances = bim_doc.get("instances", [])
    target = next((i for i in instances if i.get("id") == instance_id), None)
    if target is None:
        return err_payload(f"instance \"{instance_id}\" not found in host file", "NOT_FOUND")

    # Validate new params against family if family is available
    family_id = target.get("family_id")
    if family_id:
        try:
            fam_fid = _uuid.UUID(family_id)
            fam_row = await ctx.pool.fetchrow(
                "SELECT content FROM files WHERE id = $1 AND project_id = $2 AND kind = 'family' AND deleted_at IS NULL",
                fam_fid, ctx.project_id,
            )
            if fam_row:
                family_doc = json.loads(fam_row["content"])
                merged_instance = {**target, "params": {**target.get("params", {}), **new_params}}
                resolved = resolve_params(family_doc, merged_instance)
                param_defs = {p["name"]: p for p in family_doc.get("params", [])}
                param_errors = []
                for pname, value in resolved.items():
                    defn = param_defs.get(pname)
                    if not defn:
                        continue
                    if defn.get("type") == "number":
                        mn, mx = defn.get("min"), defn.get("max")
                        if mn is not None and value < mn:
                            param_errors.append(f"param \"{pname}\": {value} is below min {mn}")
                        if mx is not None and value > mx:
                            param_errors.append(f"param \"{pname}\": {value} is above max {mx}")
                    if defn.get("type") == "enum":
                        if value not in defn.get("options", []):
                            param_errors.append(f"param \"{pname}\": \"{value}\" is not a valid option")
                if param_errors:
                    return err_payload("; ".join(param_errors), "VALIDATION_ERROR")
        except Exception:
            pass  # if family lookup fails, allow update (graceful degradation)

    target.setdefault("params", {}).update(new_params)
    body = json.dumps(bim_doc, indent="  ")

    await ctx.pool.execute(
        "UPDATE files SET content = $1 WHERE id = $2 AND project_id = $3",
        body, host_fid, ctx.project_id,
    )
    await record_revision_for_file(ctx, host_fid, body, "tool")

    return ok_payload({"instance_id": instance_id, "params": target["params"]})
