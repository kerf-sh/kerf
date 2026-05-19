import json
import re
import uuid
from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx
from kerf_core.revisions import write_revision as _write_revision

# Path-resolution helpers live in file_ops — re-export so the rest of
# this module is unchanged. The local copies queried a non-existent
# `path` column on `files` and 500'd every scaffold tool call.
from kerf_api.tools.file_ops import resolve_path, ensure_folders  # noqa: F401


async def record_revision_for_file(ctx: ProjectCtx, file_id: uuid.UUID, content: str, source: str):
    cap = ctx.file_revisions_max if ctx.file_revisions_max > 0 else 200
    user_id = ctx.user_id if ctx.user_id != uuid.UUID(int=0) else None
    return await _write_revision(
        pool=ctx.pool,
        file_id=file_id,
        content=content,
        source=source,
        user_id=user_id,
        cap=cap,
    )


create_sketch_spec = ToolSpec(
    name="create_sketch",
    description="Create a new parametric 2D sketch file. The user authors geometry + dimensional/geometric constraints in the sketch UI; LLM tools cannot mutate sketches beyond creation. Sketches compile to a JSCAD Geom2 and can be imported by `.jscad` files via `import profile from '/path.sketch'`.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "plane": {"type": "string", "enum": ["XY", "XZ", "YZ"]},
            "name": {"type": "string"},
            "description": {"type": "string"},
        },
        "required": ["path"],
    },
)


@register(create_sketch_spec, write=True)
async def run_create_sketch(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path = a.get("path", "")
    plane = a.get("plane", "XY").upper()
    name = a.get("name", "")
    description = a.get("description", "")

    if plane not in ("XY", "XZ", "YZ"):
        return err_payload("plane must be XY|XZ|YZ", "BAD_ARGS")

    clean = path.rstrip("/")
    if not clean.startswith("/"):
        return err_payload("path must be absolute", "BAD_ARGS")

    parts = [p for p in clean.strip("/").split("/") if p]
    if not parts:
        return err_payload("cannot create the root", "BAD_ARGS")

    if not clean.lower().endswith(".sketch"):
        clean = clean + ".sketch"
        parts = [p for p in clean.strip("/").split("/") if p]

    rp = await resolve_path(ctx, clean)
    if rp.get("exists"):
        return err_payload("path already exists", "EXISTS")

    doc = {
        "version": 1,
        "plane": {"type": "base", "name": plane},
        "entities": [{"id": "origin", "type": "point", "x": 0, "y": 0}],
        "constraints": [],
        "visible_3d": [],
        "solved": {},
        "metadata": {"name": name, "description": description},
    }

    body = json.dumps(doc, indent="  ")

    parent_id = await ensure_folders(ctx, parts[:-1])
    leaf = parts[-1]

    new_id = await ctx.pool.fetchval(
        "INSERT INTO files(project_id, parent_id, name, kind, content) VALUES ($1, $2, $3, 'sketch', $4) RETURNING id",
        ctx.project_id, parent_id, leaf, body,
    )
    await record_revision_for_file(ctx, new_id, body, "tool")

    return ok_payload({"path": clean, "id": str(new_id), "plane": plane})


create_feature_spec = ToolSpec(
    name="create_feature",
    description="Create a new empty .feature file (OCCT B-rep timeline). After creation, append operations by editing the JSON via write_file / edit_file. Consult docs/llm/feature.md for the node-type vocabulary (pad / pocket / revolve / fillet / chamfer / shell / hole). Refuses .sketch / .assembly / .drawing / .part paths.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "name": {"type": "string"},
        },
        "required": ["path"],
    },
)


@register(create_feature_spec, write=True)
async def run_create_feature(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path = a.get("path", "")
    name = a.get("name", "")

    clean = path.rstrip("/")
    if not clean.startswith("/"):
        return err_payload("path must be absolute", "BAD_ARGS")

    parts = [p for p in clean.strip("/").split("/") if p]
    if not parts:
        return err_payload("cannot create the root", "BAD_ARGS")

    if not clean.lower().endswith(".feature"):
        clean = clean + ".feature"
        parts = [p for p in clean.strip("/").split("/") if p]

    rp = await resolve_path(ctx, clean)
    if rp.get("exists"):
        return err_payload("path already exists", "EXISTS")

    doc = {"version": 1, "name": name, "features": []}
    body = json.dumps(doc, indent="  ")

    parent_id = await ensure_folders(ctx, parts[:-1])
    leaf = parts[-1]

    new_id = await ctx.pool.fetchval(
        "INSERT INTO files(project_id, parent_id, name, kind, content) VALUES ($1, $2, $3, 'feature', $4) RETURNING id",
        ctx.project_id, parent_id, leaf, body,
    )
    await record_revision_for_file(ctx, new_id, body, "tool")

    return ok_payload({"path": clean, "id": str(new_id)})


create_part_spec = ToolSpec(
    name="create_part",
    description="Create a new Part file (kind='part') in the library. The Part stores manufacturer/MPN/distributor metadata as JSON; assemblies reference parts as Components and the BOM endpoint rolls them up. `name` is required; everything else can be filled in later by editing the file via write_file / edit_file.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "metadata": {"type": "object"},
        },
        "required": ["path", "metadata"],
    },
)


@register(create_part_spec, write=True)
async def run_create_part(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path = a.get("path", "")
    metadata = a.get("metadata", {})

    if not metadata.get("name"):
        return err_payload("metadata.name is required", "BAD_ARGS")

    clean = path.rstrip("/")
    if not clean.startswith("/"):
        return err_payload("path must be absolute", "BAD_ARGS")

    parts = [p for p in clean.strip("/").split("/") if p]
    if not parts:
        return err_payload("cannot create the root", "BAD_ARGS")

    if not clean.lower().endswith(".part"):
        clean = clean + ".part"
        parts = [p for p in clean.strip("/").split("/") if p]

    rp = await resolve_path(ctx, clean)
    if rp.get("exists"):
        return err_payload("path already exists", "EXISTS")

    doc = {
        "version": 1,
        "name": metadata.get("name", ""),
        "description": metadata.get("description", ""),
        "category": metadata.get("category", ""),
        "manufacturer": metadata.get("manufacturer", ""),
        "mpn": metadata.get("mpn", ""),
        "value": metadata.get("value", ""),
        "datasheet_url": metadata.get("datasheet_url", ""),
        "distributors": metadata.get("distributors", []),
        "metadata": metadata.get("metadata", {}),
    }
    body = json.dumps(doc, indent="  ")

    parent_id = await ensure_folders(ctx, parts[:-1])
    leaf = parts[-1]

    new_id = await ctx.pool.fetchval(
        "INSERT INTO files(project_id, parent_id, name, kind, content) VALUES ($1, $2, $3, 'part', $4) RETURNING id",
        ctx.project_id, parent_id, leaf, body,
    )
    await record_revision_for_file(ctx, new_id, body, "tool")

    return ok_payload({"path": clean, "id": str(new_id), "name": doc["name"]})


create_circuit_spec = ToolSpec(
    name="create_circuit",
    description="Create a new tscircuit electronics-design file (`.circuit.tsx`). The user authors components + traces in JSX; the editor compiles to schematic, PCB, and 3D views via tscircuit.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "name": {"type": "string"},
            "width_mm": {"type": "number"},
            "height_mm": {"type": "number"},
        },
        "required": ["path"],
    },
)


@register(create_circuit_spec, write=True)
async def run_create_circuit(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path = a.get("path", "")
    name = a.get("name", "")
    w = a.get("width_mm", 20)
    h = a.get("height_mm", 20)

    clean = path.rstrip("/")
    if not clean.startswith("/"):
        return err_payload("path must be absolute", "BAD_ARGS")

    parts = [p for p in clean.strip("/").split("/") if p]
    if not parts:
        return err_payload("cannot create the root", "BAD_ARGS")

    if not clean.lower().endswith(".circuit.tsx"):
        clean = clean + ".circuit.tsx"
        parts = [p for p in clean.strip("/").split("/") if p]

    rp = await resolve_path(ctx, clean)
    if rp.get("exists"):
        return err_payload("path already exists", "EXISTS")

    body = f'''import {{ Circuit }} from "tscircuit"

export default (
  <board width="{w}mm" height="{h}mm">
  </board>
)'''

    parent_id = await ensure_folders(ctx, parts[:-1])
    leaf = parts[-1]

    new_id = await ctx.pool.fetchval(
        "INSERT INTO files(project_id, parent_id, name, kind, content) VALUES ($1, $2, $3, 'circuit', $4) RETURNING id",
        ctx.project_id, parent_id, leaf, body,
    )
    await record_revision_for_file(ctx, new_id, body, "tool")

    return ok_payload({"path": clean, "id": str(new_id), "width_mm": w, "height_mm": h})


add_probe_spec = ToolSpec(
    name="add_probe",
    description="Add a SPICE simulation probe to a `.circuit.tsx` file. The probe references a schematic port (V) or component (I) and becomes a `.print` directive in the generated SPICE netlist.",
    input_schema={
        "type": "object",
        "properties": {
            "circuit_file_id": {"type": "string"},
            "name": {"type": "string"},
            "kind": {"type": "string", "enum": ["V", "I"]},
            "target_id": {"type": "string"},
        },
        "required": ["circuit_file_id", "name", "kind", "target_id"],
    },
)


@register(add_probe_spec, write=True)
async def run_add_probe(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_file_id = a.get("circuit_file_id", "")
    name = a.get("name", "")
    kind = a.get("kind", "")
    target_id = a.get("target_id", "")

    if not circuit_file_id or not name or not kind or not target_id:
        return err_payload("circuit_file_id, name, kind, and target_id are required", "BAD_ARGS")

    if kind not in ("V", "I"):
        return err_payload("kind must be 'V' (voltage) or 'I' (current)", "BAD_ARGS")

    if not re.match(r"^[A-Za-z0-9_-]+$", name):
        return err_payload("name must match [A-Za-z0-9_-]+", "BAD_ARGS")

    try:
        fid = uuid.UUID(circuit_file_id)
    except Exception:
        return err_payload("circuit_file_id must be a uuid", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        "SELECT kind, content FROM files WHERE id = $1 AND project_id = $2 AND deleted_at IS NULL",
        fid, ctx.project_id,
    )
    if not row:
        return err_payload("circuit file not found", "NOT_FOUND")

    if row["kind"] != "circuit":
        return err_payload("file is not a circuit", "BAD_KIND")

    content = row["content"] or ""

    probe_line = f"// @kerf-probe NAME={name} KIND={kind} TARGET={target_id}\n"
    new_content = content + "\n" + probe_line

    await ctx.pool.execute(
        "UPDATE files SET content = $1, updated_at = now() WHERE id = $2 AND project_id = $3",
        new_content, fid, ctx.project_id,
    )
    await record_revision_for_file(ctx, fid, new_content, "tool")

    return ok_payload({
        "circuit_file_id": circuit_file_id,
        "name": name,
        "kind": kind,
        "target_id": target_id,
    })


remove_probe_spec = ToolSpec(
    name="remove_probe",
    description="Remove a SPICE simulation probe from a `.circuit.tsx` file by name. The matching `// @kerf-probe NAME=<name> ...` comment line is deleted. Tolerant: succeeds without error if no such probe exists.",
    input_schema={
        "type": "object",
        "properties": {
            "circuit_file_id": {"type": "string"},
            "name": {"type": "string"},
        },
        "required": ["circuit_file_id", "name"],
    },
)


@register(remove_probe_spec, write=True)
async def run_remove_probe(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_file_id = a.get("circuit_file_id", "")
    name = a.get("name", "")

    if not circuit_file_id or not name:
        return err_payload("circuit_file_id and name are required", "BAD_ARGS")

    try:
        fid = uuid.UUID(circuit_file_id)
    except Exception:
        return err_payload("circuit_file_id must be a uuid", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        "SELECT kind, content FROM files WHERE id = $1 AND project_id = $2 AND deleted_at IS NULL",
        fid, ctx.project_id,
    )
    if not row:
        return err_payload("circuit file not found", "NOT_FOUND")

    if row["kind"] != "circuit":
        return err_payload("file is not a circuit", "BAD_KIND")

    content = row["content"] or ""

    pattern = rf"// @kerf-probe NAME={re.escape(name)} .*\n?"
    new_content = re.sub(pattern, "", content)

    if new_content == content:
        return ok_payload({
            "circuit_file_id": circuit_file_id,
            "name": name,
            "removed": False,
        })

    await ctx.pool.execute(
        "UPDATE files SET content = $1, updated_at = now() WHERE id = $2 AND project_id = $3",
        new_content, fid, ctx.project_id,
    )
    await record_revision_for_file(ctx, fid, new_content, "tool")

    return ok_payload({
        "circuit_file_id": circuit_file_id,
        "name": name,
        "removed": True,
    })


rename_probe_spec = ToolSpec(
    name="rename_probe",
    description="Rename a SPICE simulation probe in a `.circuit.tsx` file. Rewrites the NAME field of the matching `// @kerf-probe` line, leaving KIND/PORT untouched. Tolerant: succeeds without error if no such probe exists.",
    input_schema={
        "type": "object",
        "properties": {
            "circuit_file_id": {"type": "string"},
            "old_name": {"type": "string"},
            "new_name": {"type": "string"},
        },
        "required": ["circuit_file_id", "old_name", "new_name"],
    },
)


@register(rename_probe_spec, write=True)
async def run_rename_probe(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_file_id = a.get("circuit_file_id", "")
    old_name = a.get("old_name", "")
    new_name = a.get("new_name", "")

    if not circuit_file_id or not old_name or not new_name:
        return err_payload("circuit_file_id, old_name, and new_name are required", "BAD_ARGS")

    if old_name == new_name:
        return err_payload("old_name and new_name are identical", "BAD_ARGS")

    try:
        fid = uuid.UUID(circuit_file_id)
    except Exception:
        return err_payload("circuit_file_id must be a uuid", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        "SELECT kind, content FROM files WHERE id = $1 AND project_id = $2 AND deleted_at IS NULL",
        fid, ctx.project_id,
    )
    if not row:
        return err_payload("circuit file not found", "NOT_FOUND")

    if row["kind"] != "circuit":
        return err_payload("file is not a circuit", "BAD_KIND")

    content = row["content"] or ""

    pattern = rf"(// @kerf-probe NAME=)({re.escape(old_name)})( .*)"
    replacement = rf"\g<1>{new_name}\3"
    new_content, count = re.subn(pattern, replacement, content)

    if count == 0:
        return ok_payload({
            "circuit_file_id": circuit_file_id,
            "old_name": old_name,
            "new_name": new_name,
            "renamed": False,
        })

    await ctx.pool.execute(
        "UPDATE files SET content = $1, updated_at = now() WHERE id = $2 AND project_id = $3",
        new_content, fid, ctx.project_id,
    )
    await record_revision_for_file(ctx, fid, new_content, "tool")

    return ok_payload({
        "circuit_file_id": circuit_file_id,
        "old_name": old_name,
        "new_name": new_name,
        "renamed": True,
    })