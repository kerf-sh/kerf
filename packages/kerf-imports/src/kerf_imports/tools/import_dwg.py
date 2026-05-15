"""
import_dwg.py — LLM tool: import_dwg (T-8).

Reads an uploaded DWG file and creates:
  - One ``.sketch`` file containing geometry entities (LINE, LWPOLYLINE,
    POLYLINE, CIRCLE, ARC) mapped to Kerf's Geom2 format.
  - One ``.drawing`` file containing annotation entities (TEXT, MTEXT).

Both files are created inside a folder (``import_folder``) in the target
project.  If a file would be empty it is omitted.

The tool requires the optional ``libredwg`` bridge (either the Python
binding or the ``dwgread`` CLI).  When the bridge is absent the tool
returns ``{ok: false, reason: "DWG bridge not available — install libredwg"}``.

The actual conversion chain is::

    .dwg bytes
      → libredwg bridge → DXF ASCII text
      → kerf_imports.dxf.reader.read_dxf_bytes()
      → kerf_imports.dxf.mapper.dxf_to_both()
      → Kerf .sketch / .drawing JSON payloads

Returns::

    {
      "created_files": [
        {"file_id": "...", "name": "import.sketch", "kind": "sketch"},
        {"file_id": "...", "name": "import.drawing", "kind": "drawing"}
      ],
      "stats": {
        "entities": N,
        "annotations": N,
        "blocks": N,
        "warnings": N,
        "loops": N
      },
      "warnings": [...],
      "import_folder": "/dwg_import",
      "bridge": {"available": true, "backend": "cli"|"python", "version": "..."}
    }
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from kerf_core.utils.context import ProjectCtx
from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register

from kerf_imports.dwg.bridge import (
    dwg_bridge_available,
    convert_dwg_to_dxf,
    get_bridge_info,
    DwgBridgeUnavailable,
    DwgConversionError,
)
from kerf_imports.dxf.reader import read_dxf
from kerf_imports.dxf.mapper import dxf_to_both, find_closed_loops

# ---------------------------------------------------------------------------
# Spec
# ---------------------------------------------------------------------------

import_dwg_spec = ToolSpec(
    name="import_dwg",
    description=(
        "Import a DWG (AutoCAD Drawing) file into a Kerf project. "
        "Requires the optional libredwg bridge (Python binding or dwgread CLI). "
        "If the bridge is absent, returns {ok:false, reason:'DWG bridge not available'}. "
        "When available, converts the DWG to DXF internally and routes all entities "
        "through the same DXF mapper pipeline: geometry → .sketch file, "
        "text annotations → .drawing file. "
        "Supports all DWG versions that libredwg can read (R1.0 through 2018+). "
        "Returns the list of created files, stats, and any translation warnings."
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
                "description": "Blob ID or storage key for the uploaded .dwg file.",
            },
            "import_folder": {
                "type": "string",
                "description": (
                    "Folder path inside the project tree for imported files. "
                    "Defaults to /dwg_import."
                ),
            },
            "expand_inserts": {
                "type": "boolean",
                "description": (
                    "When true (default) INSERT block references are expanded inline. "
                    "When false they are emitted as insert placeholder entities."
                ),
            },
        },
        "required": ["project_id", "file_blob_id_or_storage_key"],
    },
)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

@register(import_dwg_spec, write=True)
async def import_dwg(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    project_id    = a.get("project_id", "").strip()
    blob_ref      = a.get("file_blob_id_or_storage_key", "").strip()
    import_folder = (a.get("import_folder") or "/dwg_import").strip() or "/dwg_import"
    expand_inserts = bool(a.get("expand_inserts", True))

    if not project_id:
        return err_payload("project_id is required", "BAD_ARGS")
    if not blob_ref:
        return err_payload("file_blob_id_or_storage_key is required", "BAD_ARGS")

    # ── Check bridge availability before touching storage ────────────────────
    bridge_info = get_bridge_info()
    if not bridge_info["available"]:
        return err_payload(
            "DWG bridge not available — install libredwg "
            "(pip install libredwg  OR  brew install libredwg)",
            "DWG_BRIDGE_UNAVAILABLE",
        )

    # ── Resolve blob → bytes ─────────────────────────────────────────────────
    if ctx.storage is None:
        return err_payload("storage backend not configured", "NO_STORAGE")

    try:
        blob_bytes = await ctx.storage.get(blob_ref)
    except Exception as exc:
        return err_payload(f"failed to fetch blob {blob_ref!r}: {exc}", "STORAGE_ERROR")

    if not blob_bytes:
        return err_payload(f"blob not found: {blob_ref}", "NOT_FOUND")

    # ── DWG → DXF conversion ─────────────────────────────────────────────────
    try:
        dxf_text = convert_dwg_to_dxf(blob_bytes)
    except DwgBridgeUnavailable as exc:
        return err_payload(str(exc), "DWG_BRIDGE_UNAVAILABLE")
    except DwgConversionError as exc:
        return err_payload(f"DWG conversion failed: {exc}", "DWG_CONVERSION_ERROR")
    except Exception as exc:
        return err_payload(f"unexpected DWG conversion error: {exc}", "DWG_CONVERSION_ERROR")

    if not dxf_text or not dxf_text.strip():
        return err_payload("DWG conversion produced empty DXF output", "DWG_CONVERSION_ERROR")

    # ── DXF parse + map ──────────────────────────────────────────────────────
    try:
        doc = read_dxf(dxf_text)
    except Exception as exc:
        return err_payload(f"DXF parse error after DWG conversion: {exc}", "DXF_PARSE_ERROR")

    try:
        sketch_payload, drawing_payload = dxf_to_both(doc, expand_inserts=expand_inserts)
    except Exception as exc:
        return err_payload(f"DXF mapping error: {exc}", "DXF_MAPPING_ERROR")

    # Detect closed loops in the sketch
    try:
        loops = find_closed_loops(sketch_payload)
        sketch_payload["loops"] = [[eid for eid in loop] for loop in loops]
    except Exception:
        loops = []

    # ── Build file list ──────────────────────────────────────────────────────
    sketch_entities = sketch_payload.get("entities", [])
    drawing_annotations = (
        drawing_payload.get("sheets", [{}])[0].get("annotations", [])
    )

    files_to_create: list[tuple[str, str, dict]] = []
    if sketch_entities:
        files_to_create.append(("import.sketch", "sketch", sketch_payload))
    if drawing_annotations:
        files_to_create.append(("import.drawing", "drawing", drawing_payload))

    # ── Ensure import folder ─────────────────────────────────────────────────
    folder_path = import_folder.rstrip("/")
    if not folder_path.startswith("/"):
        folder_path = "/" + folder_path

    folder_id = await _ensure_folder(ctx, folder_path)

    # ── Persist files ────────────────────────────────────────────────────────
    created_files: list[dict[str, Any]] = []
    warnings: list[str] = list(doc.warnings)

    for name, db_kind, payload in files_to_create:
        content_str = json.dumps(payload)
        try:
            new_id = await ctx.pool.fetchval(
                """INSERT INTO files(id, project_id, parent_id, name, kind, content)
                   VALUES ($1, $2, $3, $4, $5, $6)
                   RETURNING id""",
                uuid.uuid4(),
                ctx.project_id,
                folder_id,
                name,
                db_kind,
                content_str,
            )
            created_files.append({
                "file_id": str(new_id),
                "name": name,
                "kind": db_kind,
            })
        except Exception as exc:
            warnings.append(f"failed to insert {name!r}: {exc}")
            created_files.append({
                "file_id": None,
                "name": name,
                "kind": db_kind,
                "error": str(exc),
            })

    all_warnings = list(doc.warnings)
    all_warnings.extend(sketch_payload.get("warnings", []))
    seen: set[str] = set()
    deduped: list[str] = []
    for w in all_warnings:
        if w not in seen:
            seen.add(w)
            deduped.append(w)

    stats = {
        "entities":    len(sketch_entities),
        "annotations": len(drawing_annotations),
        "blocks":      len(doc.blocks),
        "warnings":    len(deduped),
        "loops":       len(loops),
    }

    return ok_payload({
        "created_files": created_files,
        "stats": stats,
        "warnings": deduped,
        "import_folder": folder_path,
        "bridge": bridge_info,
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _ensure_folder(ctx: ProjectCtx, folder_path: str) -> Any:
    """Create the folder hierarchy and return the leaf folder id."""
    parts = [p for p in folder_path.strip("/").split("/") if p]
    if not parts:
        return None

    parent_id = None
    for part in parts:
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


# ---------------------------------------------------------------------------
# TOOLS registration list
# ---------------------------------------------------------------------------

TOOLS = [
    (
        "import_dwg",
        import_dwg_spec,
        import_dwg,
    ),
]
