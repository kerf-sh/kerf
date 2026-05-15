"""
import_freecad.py — LLM tool: import_freecad_project.

Mirrors the shape of import_3dm:
  1. Fetch the .FCStd blob from storage.
  2. POST to pyworker /import-freecad-project.
  3. Walk the response: create sketch / feature / assembly files in PG.
  4. Return structured {created_files, stats, warnings, import_folder}.

Handles mode: "project" | "library":
  - "project" (default): files land under import_folder in the project tree.
  - "library": same folder layout but would land under the user's Library root
    (in Tier 1 this is the same code-path; the distinction is reserved for
    Tier 2 when Library-mode endpoints are wired).
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Any

from kerf_core.utils.context import ProjectCtx
from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register

# ---------------------------------------------------------------------------
# Spec
# ---------------------------------------------------------------------------

import_freecad_project_spec = ToolSpec(
    name="import_freecad_project",
    description=(
        "Import a FreeCAD .FCStd file into a new (or existing) Kerf project. "
        "Creates one .feature file per PartDesign::Body, one .sketch per "
        "Sketcher::SketchObject, an .assembly if there is more than one body, "
        "and lifts the cached BRep blobs from the archive losslessly. "
        "Tier 2 additions: Spreadsheet::Sheet → .equations (named cell "
        "parameters), TechDraw::DrawPage → .drawing (projected views), and "
        "App::MaterialObject → .material (density, modulus, color, etc.). "
        "Tier 3 additions: PartDesign::Plane/Line/Point datums → datum_attachment "
        "metadata on sketch planes; Draft Workbench objects → .sketch files "
        "(Draft::Wire, Rectangle, Circle, Polygon, Ellipse, BSpline) and "
        ".feature files (Draft::Array, Clone, Mirror). Unsupported Draft types "
        "warn-and-skip. "
        "The imported feature-tree metadata is read-only — geometry is the "
        "lifted BRep, not a recompute. Returns the list of created files and "
        "translation warnings."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {
                "type": "string",
                "description": "UUID of the target Kerf project. Required for project-import mode.",
            },
            "file_blob_id_or_storage_key": {
                "type": "string",
                "description": "Blob ID or storage key for the uploaded .FCStd file.",
            },
            "import_folder": {
                "type": "string",
                "description": "Path inside the project tree where imported files will be placed. Defaults to /freecad_import.",
            },
            "mode": {
                "type": "string",
                "enum": ["project", "library"],
                "description": "Import mode: 'project' (default) creates files inside the project, 'library' imports as Library Parts.",
            },
        },
        "required": ["project_id", "file_blob_id_or_storage_key"],
    },
)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

@register(import_freecad_project_spec, write=True)
async def import_freecad_project(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    project_id = a.get("project_id", "").strip()
    blob_ref = a.get("file_blob_id_or_storage_key", "").strip()
    import_folder = a.get("import_folder", "/freecad_import").strip() or "/freecad_import"
    mode = a.get("mode", "project").strip() or "project"

    if not project_id:
        return err_payload("project_id is required", "BAD_ARGS")
    if not blob_ref:
        return err_payload("file_blob_id_or_storage_key is required", "BAD_ARGS")
    if mode not in ("project", "library"):
        return err_payload("mode must be 'project' or 'library'", "BAD_ARGS")

    # ── Resolve blob → bytes ─────────────────────────────────────────────────
    if ctx.storage is None:
        return err_payload("storage backend not configured", "NO_STORAGE")

    try:
        blob_bytes = await ctx.storage.get(blob_ref)
    except Exception as exc:
        return err_payload(f"failed to fetch blob {blob_ref!r}: {exc}", "STORAGE_ERROR")

    if not blob_bytes:
        return err_payload(f"blob not found: {blob_ref}", "NOT_FOUND")

    # ── Call pyworker /import-freecad-project ────────────────────────────────
    import httpx

    pyworker_url = os.getenv("PYWORKER_URL", "http://localhost:8090")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0)) as client:
            resp = await client.post(
                f"{pyworker_url}/import-freecad-project",
                files={
                    "file": (
                        "upload.FCStd",
                        blob_bytes,
                        "application/octet-stream",
                    )
                },
                params={"import_folder": import_folder},
            )
        if resp.status_code == 422:
            detail = resp.json().get("detail", resp.text[:400])
            return err_payload(
                f"FCStd format error: {detail}", "FREECAD_FORMAT_ERROR"
            )
        if resp.status_code != 200:
            return err_payload(
                f"pyworker error {resp.status_code}: {resp.text[:400]}", "PYWORKER_ERROR"
            )
        data = resp.json()
    except Exception as exc:
        return err_payload(f"failed to reach pyworker: {exc}", "PYWORKER_UNREACHABLE")

    pyworker_warnings: list[str] = data.get("warnings") or []
    files: list[dict] = data.get("created_files") or []
    stats: dict = data.get("stats") or {}

    # ── Upload BRep blobs from assets ────────────────────────────────────────
    # (Tier 1: pyworker returns inline payload + placeholder_id.
    #  The actual BRep bytes are embedded in the payload nodes for now.
    #  Tier 2 will add a separate /blob endpoint; for Tier 1 we skip
    #  the upload step and leave the placeholder_id as-is — the frontend
    #  will see the placeholder and can resolve it once Tier 2 lands.)

    # ── Resolve import folder ────────────────────────────────────────────────
    folder_path = import_folder.rstrip("/")
    if not folder_path.startswith("/"):
        folder_path = "/" + folder_path

    folder_id = await _ensure_folder(ctx, folder_path)

    # Extension → DB kind mapping
    _kind_to_db = {
        "feature": "feature",
        "sketch": "sketch",
        "assembly": "assembly",
        "equations": "equations",
        "drawing": "drawing",
        "material": "material",
        "file": "file",
    }

    created_files: list[dict[str, Any]] = []
    warnings: list[str] = list(pyworker_warnings)

    for f in files:
        name = f.get("name", "unnamed")
        kerf_kind = f.get("kind", "file")
        payload = f.get("payload", {})
        db_kind = _kind_to_db.get(kerf_kind, "file")
        content_str = json.dumps(payload) if isinstance(payload, dict) else str(payload)

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
                "freecad_name": f.get("freecad_name"),
                "placeholder_id": f.get("placeholder_id"),
            })
        except Exception as exc:
            # Log + continue — don't abort whole import for one bad file
            warnings.append(f"failed to insert {name!r}: {exc}")
            created_files.append({
                "file_id": None,
                "name": name,
                "kind": db_kind,
                "freecad_name": f.get("freecad_name"),
                "placeholder_id": f.get("placeholder_id"),
                "error": str(exc),
            })

    return ok_payload({
        "created_files": created_files,
        "stats": stats,
        "warnings": warnings,
        "import_folder": folder_path,
    })


# ---------------------------------------------------------------------------
# Helpers (shared with import_3dm pattern)
# ---------------------------------------------------------------------------

async def _ensure_folder(ctx: ProjectCtx, folder_path: str) -> Any:
    """Create the folder hierarchy for folder_path and return the leaf folder id."""
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
# TOOLS registration list (kerf_imports/plugin.py pattern)
# ---------------------------------------------------------------------------

TOOLS = [
    (
        "import_freecad_project",
        import_freecad_project_spec,
        import_freecad_project,
    ),
]
