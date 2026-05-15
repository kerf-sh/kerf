"""
export_ifc.py — LLM tool: export_ifc.

Converts a Kerf .bim building model (by file_id or inline dict) into an IFC
STEP-physical-file (.ifc).  The output can be:
  - Written to a project file (returns file_id)
  - Returned inline as ifc_text (for small models or preview)

Spec parameters:
    project_id   UUID of the Kerf project.
    bim_file_id  (optional) File ID of an existing .bim file in the project.
    model        (optional) Inline .bim model dict (alternative to bim_file_id).
    schema       "IFC2X3" (default) or "IFC4".
    output_path  (optional) Project-tree path for the output .ifc file.
                 If omitted the IFC text is returned inline.
"""
from __future__ import annotations

import json
from typing import Any

# ---------------------------------------------------------------------------
# Spec — defined without kerf_chat dependency so tests are hermetic
# ---------------------------------------------------------------------------

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register  # type: ignore
    from kerf_core.utils.context import ProjectCtx  # type: ignore
    _HAVE_REGISTRY = True
except ImportError:
    _HAVE_REGISTRY = False
    ToolSpec = dict          # type: ignore
    ProjectCtx = object      # type: ignore

    def register(spec, **kwargs):   # type: ignore
        def _dec(fn):
            return fn
        return _dec

    def err_payload(msg: str, code: str = "") -> str:  # type: ignore
        return json.dumps({"ok": False, "error": msg, "code": code})

    def ok_payload(data: Any) -> str:  # type: ignore
        return json.dumps({"ok": True, **data})


if _HAVE_REGISTRY:
    export_ifc_spec = ToolSpec(
        name="export_ifc",
        description=(
            "Export a Kerf building model to an IFC (.ifc) STEP-physical-file. "
            "Accepts a .bim file ID from the project or an inline model dict. "
            "Tier 1: emits IfcWall, IfcSlab, IfcColumn, IfcBeam, IfcDoor, "
            "IfcWindow with IfcExtrudedAreaSolid geometry; spatial structure "
            "IfcProject → IfcSite → IfcBuilding → IfcBuildingStorey; SI-metre units. "
            "Returns {ifc_path, entity_count, schema, warnings} or "
            "{ifc_text, entity_count, schema, warnings} when output_path is omitted."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "UUID of the Kerf project.",
                },
                "bim_file_id": {
                    "type": "string",
                    "description": "File ID of an existing .bim file to export.",
                },
                "model": {
                    "type": "object",
                    "description": (
                        "Inline .bim model dict.  Use when you have the model "
                        "in-memory rather than as a stored file."
                    ),
                },
                "schema": {
                    "type": "string",
                    "enum": ["IFC2X3", "IFC4"],
                    "description": "IFC schema version (default: IFC2X3).",
                },
                "output_path": {
                    "type": "string",
                    "description": (
                        "Project-tree path for the output .ifc file "
                        "(e.g. /exports/building.ifc).  "
                        "Omit to receive the IFC text inline."
                    ),
                },
            },
            "required": ["project_id"],
        },
    )

    @register(export_ifc_spec, write=True)
    async def export_ifc(ctx: ProjectCtx, args: bytes) -> str:
        try:
            a = json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        project_id  = a.get("project_id", "").strip()
        bim_file_id = (a.get("bim_file_id") or "").strip()
        inline_model = a.get("model")
        schema      = (a.get("schema") or "IFC2X3").strip().upper()
        output_path = (a.get("output_path") or "").strip()

        if not project_id:
            return err_payload("project_id is required", "BAD_ARGS")
        if schema not in ("IFC2X3", "IFC4"):
            return err_payload("schema must be 'IFC2X3' or 'IFC4'", "BAD_ARGS")
        if not bim_file_id and inline_model is None:
            return err_payload("one of bim_file_id or model is required", "BAD_ARGS")

        # ── Resolve model ────────────────────────────────────────────────────
        model: dict
        if inline_model is not None:
            model = inline_model
        else:
            row = await ctx.pool.fetchrow(
                "SELECT content FROM files WHERE id = $1 AND project_id = $2 "
                "AND kind = 'bim' AND deleted_at IS NULL",
                bim_file_id, project_id,
            )
            if not row:
                return err_payload(
                    f"bim file {bim_file_id!r} not found in project {project_id!r}",
                    "NOT_FOUND",
                )
            try:
                model = json.loads(row["content"])
            except Exception as exc:
                return err_payload(f"failed to parse .bim content: {exc}", "PARSE_ERROR")

        # ── Export ───────────────────────────────────────────────────────────
        try:
            from kerf_bim.export_ifc import export_ifc as _export_fn, IFCExportError
            result = _export_fn(model, schema=schema)
        except IFCExportError as exc:
            return err_payload(str(exc), "EXPORT_ERROR")
        except Exception as exc:
            return err_payload(f"unexpected export error: {exc}", "EXPORT_ERROR")

        # ── Output ───────────────────────────────────────────────────────────
        if output_path:
            import uuid
            # Ensure parent folder exists
            path_parts = [p for p in output_path.strip("/").split("/") if p]
            filename = path_parts[-1] if path_parts else "export.ifc"
            folder_parts = path_parts[:-1]

            parent_id = None
            for part in folder_parts:
                existing = await ctx.pool.fetchrow(
                    """SELECT id FROM files
                       WHERE project_id = $1 AND name = $2
                         AND parent_id IS NOT DISTINCT FROM $3
                         AND kind = 'folder' AND deleted_at IS NULL""",
                    project_id, part, parent_id,
                )
                if existing:
                    parent_id = existing["id"]
                else:
                    parent_id = await ctx.pool.fetchval(
                        """INSERT INTO files(id, project_id, parent_id, name, kind, content)
                           VALUES ($1, $2, $3, $4, 'folder', '{}') RETURNING id""",
                        uuid.uuid4(), project_id, parent_id, part,
                    )

            file_id = await ctx.pool.fetchval(
                """INSERT INTO files(id, project_id, parent_id, name, kind, content)
                   VALUES ($1, $2, $3, $4, 'ifc', $5) RETURNING id""",
                uuid.uuid4(), project_id, parent_id, filename, result.ifc_text,
            )

            return ok_payload({
                "ifc_path": output_path,
                "file_id": str(file_id),
                "entity_count": result.entity_count,
                "schema": result.schema,
                "warnings": result.warnings,
            })

        return ok_payload({
            "ifc_text": result.ifc_text,
            "entity_count": result.entity_count,
            "schema": result.schema,
            "warnings": result.warnings,
        })


# ---------------------------------------------------------------------------
# TOOLS registration list (plugin.py pattern)
# ---------------------------------------------------------------------------

if _HAVE_REGISTRY:
    TOOLS = [
        (
            "export_ifc",
            export_ifc_spec,
            export_ifc,
        ),
    ]
else:
    TOOLS = []
