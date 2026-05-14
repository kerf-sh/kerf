"""import_3dm.py — LLM tools for Rhino .3dm file import and export.

import_3dm  — posts a blob to pyworker /import-3dm, creates Kerf files
              under a folder, returns {created_files, stats}.

export_3dm  — collects Kerf file content, posts to pyworker /export-3dm,
              stores the resulting binary in blob storage, returns
              {storage_key, download_url}.
"""
import json
import os
import uuid
from typing import Any

from tools.context import ProjectCtx
from tools.registry import ToolSpec, err_payload, ok_payload, register

# ---------------------------------------------------------------------------
# Spec: import_3dm
# ---------------------------------------------------------------------------

import_3dm_spec = ToolSpec(
    name="import_3dm",
    description=(
        "Import a Rhino .3dm file into the current project. "
        "Accepts a blob_id or storage_key pointing to the uploaded .3dm binary. "
        "Classifies each Rhino object by type (BRep→feature, Curve→sketch, "
        "Surface→surf, Mesh→mesh, Point→point, InstanceReference→instance metadata) "
        "and creates corresponding Kerf files under an import folder. "
        "Returns the list of created files and object-count statistics."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {
                "type": "string",
                "description": "UUID of the target Kerf project.",
            },
            "file_blob_id_or_storage_key": {
                "type": "string",
                "description": "Blob ID or storage key returned by the file-upload endpoint for the .3dm binary.",
            },
            "import_folder": {
                "type": "string",
                "description": "Path inside the project tree where imported files will be placed. Defaults to /rhino_import.",
            },
        },
        "required": ["project_id", "file_blob_id_or_storage_key"],
    },
)


@register(import_3dm_spec, write=True)
async def import_3dm(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    project_id = a.get("project_id", "").strip()
    blob_ref = a.get("file_blob_id_or_storage_key", "").strip()
    import_folder = a.get("import_folder", "/rhino_import").strip()

    if not project_id:
        return err_payload("project_id is required", "BAD_ARGS")
    if not blob_ref:
        return err_payload("file_blob_id_or_storage_key is required", "BAD_ARGS")

    # ── Resolve blob → bytes ─────────────────────────────────────────────────
    if ctx.storage is None:
        return err_payload("storage backend not configured", "NO_STORAGE")

    try:
        blob_bytes = await ctx.storage.get(blob_ref)
    except Exception as exc:
        return err_payload(f"failed to fetch blob {blob_ref!r}: {exc}", "STORAGE_ERROR")

    if not blob_bytes:
        return err_payload(f"blob not found: {blob_ref}", "NOT_FOUND")

    # ── Call pyworker /import-3dm ────────────────────────────────────────────
    import httpx

    pyworker_url = os.getenv("PYWORKER_URL", "http://localhost:8090")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            resp = await client.post(
                f"{pyworker_url}/import-3dm",
                files={"file": ("upload.3dm", blob_bytes, "application/octet-stream")},
            )
        if resp.status_code != 200:
            return err_payload(
                f"pyworker error {resp.status_code}: {resp.text[:400]}", "PYWORKER_ERROR"
            )
        data = resp.json()
    except Exception as exc:
        return err_payload(f"failed to reach pyworker: {exc}", "PYWORKER_UNREACHABLE")

    pyworker_errors = data.get("errors") or []
    if pyworker_errors:
        return err_payload(pyworker_errors[0], "PYWORKER_ERROR")

    files = data.get("files", [])
    stats = data.get("stats", {"count_by_kind": {}})

    # ── Persist files in Kerf DB ─────────────────────────────────────────────
    # Ensure target folder exists
    folder_path = import_folder.rstrip("/")
    if not folder_path.startswith("/"):
        folder_path = "/" + folder_path

    folder_id = await _ensure_folder(ctx, folder_path)

    # Extension → DB kind mapping
    _ext_to_db_kind = {
        "feature": "feature",
        "sketch": "sketch",
        "surf": "surf",
        "mesh": "mesh",
        "point": "file",
        "instance": "file",
        "unknown": "file",
    }

    created_files = []
    for f in files:
        name = f.get("name", "unnamed")
        kerf_kind = f.get("kind", "file")
        content = f.get("content", {})
        db_kind = _ext_to_db_kind.get(kerf_kind, "file")
        content_str = json.dumps(content) if isinstance(content, dict) else str(content)

        try:
            new_id = await ctx.pool.fetchval(
                """INSERT INTO files(id, project_id, parent_id, name, kind, content)
                   VALUES ($1, $2, $3, $4, $5, $6)
                   RETURNING id""",
                uuid.uuid4(), ctx.project_id, folder_id, name, db_kind, content_str,
            )
            created_files.append({
                "file_id": str(new_id),
                "name": name,
                "kind": db_kind,
                "rhino_kind": kerf_kind,
            })
        except Exception as exc:
            # Log and continue — don't abort whole import for one bad object
            created_files.append({
                "file_id": None,
                "name": name,
                "kind": db_kind,
                "rhino_kind": kerf_kind,
                "error": str(exc),
            })

    return ok_payload({
        "created_files": created_files,
        "stats": stats,
        "import_folder": folder_path,
        "layers": data.get("layers", []),
    })


# ---------------------------------------------------------------------------
# Spec: export_3dm
# ---------------------------------------------------------------------------

export_3dm_spec = ToolSpec(
    name="export_3dm",
    description=(
        "Export one or more Kerf files as a single Rhino .3dm binary. "
        "Collects the content of each file_id, posts it to pyworker /export-3dm, "
        "stores the resulting .3dm in blob storage, and returns the storage_key "
        "and a short-lived download_url."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {
                "type": "string",
                "description": "UUID of the Kerf project.",
            },
            "file_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of Kerf file UUIDs to include in the export.",
            },
            "output_filename": {
                "type": "string",
                "description": "Desired filename for the downloaded .3dm archive (default: export.3dm).",
            },
        },
        "required": ["project_id", "file_ids"],
    },
)


@register(export_3dm_spec, write=False)
async def export_3dm(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    project_id = a.get("project_id", "").strip()
    file_ids = a.get("file_ids") or []
    output_filename = a.get("output_filename", "export.3dm").strip() or "export.3dm"

    if not project_id:
        return err_payload("project_id is required", "BAD_ARGS")
    if not isinstance(file_ids, list) or len(file_ids) == 0:
        return err_payload("file_ids must be a non-empty list", "BAD_ARGS")

    if ctx.storage is None:
        return err_payload("storage backend not configured", "NO_STORAGE")

    # ── Collect file content from DB ─────────────────────────────────────────
    payload_files = []
    for fid in file_ids:
        try:
            row = await ctx.pool.fetchrow(
                "SELECT name, kind, content FROM files WHERE id = $1 AND project_id = $2 AND deleted_at IS NULL",
                uuid.UUID(fid), ctx.project_id,
            )
        except Exception as exc:
            return err_payload(f"invalid file_id {fid!r}: {exc}", "BAD_ARGS")

        if row is None:
            return err_payload(f"file not found: {fid}", "NOT_FOUND")

        try:
            content_json = json.loads(row["content"]) if row["content"] else {}
        except Exception:
            content_json = {"raw": row["content"]}

        payload_files.append({
            "kind": row["kind"],
            "content_json": content_json,
        })

    # ── Post to pyworker /export-3dm ─────────────────────────────────────────
    import httpx

    pyworker_url = os.getenv("PYWORKER_URL", "http://localhost:8090")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            resp = await client.post(
                f"{pyworker_url}/export-3dm",
                json={"files": payload_files, "layers": []},
            )
        if resp.status_code != 200:
            return err_payload(
                f"pyworker error {resp.status_code}: {resp.text[:400]}", "PYWORKER_ERROR"
            )
        blob_bytes = resp.content
    except Exception as exc:
        return err_payload(f"failed to reach pyworker: {exc}", "PYWORKER_UNREACHABLE")

    # ── Store result in blob storage ─────────────────────────────────────────
    storage_key = f"exports/{project_id}/{uuid.uuid4()}/{output_filename}"
    try:
        await ctx.storage.put(storage_key, blob_bytes, content_type="application/octet-stream")
        download_url = await ctx.storage.presign(storage_key, expires=3600)
    except Exception as exc:
        return err_payload(f"failed to store export: {exc}", "STORAGE_ERROR")

    return ok_payload({
        "storage_key": storage_key,
        "download_url": download_url,
        "filename": output_filename,
        "size_bytes": len(blob_bytes),
    })


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _ensure_folder(ctx: ProjectCtx, folder_path: str) -> Any:
    """Create the folder hierarchy for folder_path and return the leaf folder id."""
    parts = [p for p in folder_path.strip("/").split("/") if p]
    if not parts:
        return None

    parent_id = None
    for i, part in enumerate(parts):
        existing = await ctx.pool.fetchrow(
            """SELECT id FROM files
               WHERE project_id = $1 AND name = $2
                 AND parent_id IS NOT DISTINCT FROM $3
                 AND kind = 'folder'
                 AND deleted_at IS NULL""",
            ctx.project_id, part, parent_id,
        )
        if existing:
            parent_id = existing["id"]
        else:
            new_id = await ctx.pool.fetchval(
                """INSERT INTO files(id, project_id, parent_id, name, kind, content)
                   VALUES ($1, $2, $3, $4, 'folder', '{}')
                   RETURNING id""",
                uuid.uuid4(), ctx.project_id, parent_id, part,
            )
            parent_id = new_id

    return parent_id
