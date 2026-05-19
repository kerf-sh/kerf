"""
kerf_chat.tools.dispatcher — Unified tool dispatcher.

Routes the 14 catalog tool names to their underlying implementation functions.
All implementation functions are imported lazily (inside _dispatch_*) so
missing optional deps (OCC, opencamlib, blender, …) only fail at call time,
not at module import time.

Design rules:
  - This module is the ONLY place that imports per-engine/per-plugin handlers.
  - The implementations themselves (run_fem_run, run_create_sketch, …) are
    unchanged.  Only the LLM-facing name changes.
  - New engines / create kinds are added here and in catalog.py only.
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import err_payload, ok_payload
from kerf_core.utils.context import ProjectCtx


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _run(impl_fn, ctx: ProjectCtx, args: bytes) -> str:
    """Call an async implementation function, converting exceptions to errors."""
    try:
        return await impl_fn(ctx, args)
    except Exception as exc:
        return err_payload(str(exc), "ERROR")


# ---------------------------------------------------------------------------
# File-operation tools  (thin wrappers — delegate to existing implementations)
# ---------------------------------------------------------------------------

async def dispatch_read_file(ctx: ProjectCtx, args: bytes) -> str:
    from kerf_api.tools.file_ops import run_read_file
    return await _run(run_read_file, ctx, args)


async def dispatch_write_file(ctx: ProjectCtx, args: bytes) -> str:
    from kerf_api.tools.file_ops import run_write_file
    return await _run(run_write_file, ctx, args)


async def dispatch_edit_file(ctx: ProjectCtx, args: bytes) -> str:
    """edit_file with optional replace_all support.

    The existing run_edit_file replaces the first occurrence only.
    When replace_all=true we replicate the same DB round-trip but use
    str.replace (unlimited) instead of str.replace(…, 1).
    """
    from kerf_api.tools.file_ops import (
        normalize_path, resolve_path, record_revision_for_file
    )

    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    replace_all = a.get("replace_all", False)

    if not replace_all:
        # Delegate to the existing single-replace implementation.
        from kerf_api.tools.file_ops import run_edit_file
        # Strip replace_all from args so the underlying impl doesn't choke.
        a.pop("replace_all", None)
        return await _run(run_edit_file, ctx, json.dumps(a).encode())

    # replace_all=true path
    path = a.get("path", "")
    old_string = a.get("old_string", "")
    new_string = a.get("new_string", "")

    if not old_string:
        return err_payload("old_string must be non-empty", "BAD_ARGS")

    rp = await resolve_path(ctx, path)
    if not rp.get("exists"):
        return err_payload(f"file not found: {path}", "NOT_FOUND")

    kind = rp.get("kind")
    if kind in ("step", "folder"):
        return err_payload(f"cannot edit kind={kind}", "BAD_KIND")

    row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE id = $1 AND project_id = $2",
        rp["id"], ctx.project_id,
    )
    if not row:
        return err_payload(f"file not found: {path}", "NOT_FOUND")

    content = row["content"]
    count = content.count(old_string)
    if count == 0:
        return err_payload("old_string not found", "NOT_FOUND")

    updated = content.replace(old_string, new_string)
    await ctx.pool.execute(
        "UPDATE files SET content = $1, updated_at = now() WHERE id = $2 AND project_id = $3",
        updated, rp["id"], ctx.project_id,
    )
    await record_revision_for_file(ctx, rp["id"], updated, "tool")
    return ok_payload({"path": path, "replaced": count})


async def dispatch_list_files(ctx: ProjectCtx, args: bytes) -> str:
    """list_files with optional glob filter.

    The underlying run_list_files returns all files; we post-filter by glob
    if provided.
    """
    from kerf_api.tools.file_ops import run_list_files
    # Parse args to extract glob, then call the underlying impl with empty args.
    try:
        a = json.loads(args) if args else {}
    except Exception:
        a = {}
    glob_pattern = a.get("glob", "")
    # Call underlying with no args (it ignores extra keys).
    result_str = await run_list_files(ctx, b"{}")
    if not glob_pattern:
        return result_str
    # Post-filter by glob.
    import fnmatch
    try:
        result = json.loads(result_str)
        if "files" in result:
            result["files"] = [
                f for f in result["files"]
                if fnmatch.fnmatch(f.get("path", ""), glob_pattern)
            ]
        return ok_payload(result)
    except Exception:
        return result_str


async def dispatch_search_files(ctx: ProjectCtx, args: bytes) -> str:
    """search_files — delegates to existing search_code implementation."""
    from kerf_api.tools.file_ops import run_search_code
    # Remap 'pattern' → 'query' so the underlying impl gets what it expects.
    try:
        a = json.loads(args) if args else {}
    except Exception:
        return err_payload("invalid args", "BAD_ARGS")

    pattern = a.get("pattern", "")
    if not pattern:
        return err_payload("pattern is required", "BAD_ARGS")

    inner_args = json.dumps({"query": pattern, "max": a.get("max", 50)}).encode()
    return await _run(run_search_code, ctx, inner_args)


# ---------------------------------------------------------------------------
# create_file — dispatches to kind-specific scaffold implementations
# ---------------------------------------------------------------------------

async def dispatch_create_file(ctx: ProjectCtx, args: bytes) -> str:
    """create_file(kind, path, options) — routes to the matching scaffold."""
    try:
        a = json.loads(args) if args else {}
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    kind = a.get("kind", "file") or "file"
    path = a.get("path", "")
    options = a.get("options", {}) or {}

    if not path:
        return err_payload("path is required", "BAD_ARGS")

    if kind == "sketch":
        from kerf_api.tools.scaffold import run_create_sketch
        inner = {"path": path, **{k: options[k] for k in ("plane", "name", "description") if k in options}}
        return await _run(run_create_sketch, ctx, json.dumps(inner).encode())

    elif kind == "feature":
        from kerf_api.tools.scaffold import run_create_feature
        inner = {"path": path, **{k: options[k] for k in ("name",) if k in options}}
        return await _run(run_create_feature, ctx, json.dumps(inner).encode())

    elif kind == "part":
        from kerf_api.tools.scaffold import run_create_part
        metadata = options.get("metadata", {})
        inner = {"path": path, "metadata": metadata}
        return await _run(run_create_part, ctx, json.dumps(inner).encode())

    elif kind == "circuit":
        from kerf_api.tools.scaffold import run_create_circuit
        inner = {"path": path, **{k: options[k] for k in ("name", "width_mm", "height_mm") if k in options}}
        return await _run(run_create_circuit, ctx, json.dumps(inner).encode())

    elif kind in ("assembly", "drawing"):
        from kerf_api.tools.file_ops import run_create_file as _run_create_file
        inner = {"path": path, "kind": kind, "content": options.get("content", "")}
        return await _run(_run_create_file, ctx, json.dumps(inner).encode())

    elif kind == "file":
        from kerf_api.tools.file_ops import run_write_file
        content = options.get("content", "")
        inner = {"path": path, "content": content}
        return await _run(run_write_file, ctx, json.dumps(inner).encode())

    else:
        return err_payload(
            f"unknown kind '{kind}'; must be sketch|feature|part|circuit|assembly|drawing|file",
            "BAD_ARGS",
        )


# ---------------------------------------------------------------------------
# describe_part — read-only inspector
# ---------------------------------------------------------------------------

async def dispatch_describe_part(ctx: ProjectCtx, args: bytes) -> str:
    """describe_part — parse and summarise a file without full content dump."""
    try:
        a = json.loads(args) if args else {}
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path = a.get("path", "")
    part_id = a.get("part_id", "")

    if not path:
        return err_payload("path is required", "BAD_ARGS")

    from kerf_api.tools.file_ops import resolve_path
    rp = await resolve_path(ctx, path)
    if not rp.get("exists"):
        return err_payload(f"file not found: {path}", "NOT_FOUND")

    kind = rp.get("kind", "file")

    if kind == "step":
        row = await ctx.pool.fetchrow(
            "SELECT name, size, mime_type FROM files WHERE id = $1 AND project_id = $2",
            rp["id"], ctx.project_id,
        )
        if not row:
            return err_payload("file not found", "NOT_FOUND")
        return ok_payload({
            "path": path,
            "kind": kind,
            "name": row["name"],
            "size": row["size"],
            "mime_type": row["mime_type"],
        })

    row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE id = $1 AND project_id = $2",
        rp["id"], ctx.project_id,
    )
    if not row:
        return err_payload("file not found", "NOT_FOUND")

    content = row["content"] or ""
    summary: dict = {"path": path, "kind": kind}

    if kind == "sketch":
        try:
            doc = json.loads(content)
            summary["plane"] = doc.get("plane", {}).get("name", "?")
            summary["entity_count"] = len(doc.get("entities", []))
            summary["constraint_count"] = len(doc.get("constraints", []))
        except Exception:
            summary["note"] = "could not parse sketch JSON"

    elif kind == "feature":
        try:
            doc = json.loads(content)
            features = doc.get("features", [])
            summary["feature_count"] = len(features)
            summary["feature_ids"] = [f.get("id") for f in features]
            if part_id:
                match = next((f for f in features if f.get("id") == part_id), None)
                if match:
                    summary["feature"] = match
                else:
                    summary["note"] = f"feature id '{part_id}' not found"
        except Exception:
            summary["note"] = "could not parse feature JSON"

    elif kind == "assembly":
        try:
            doc = json.loads(content)
            components = doc.get("components", [])
            summary["component_count"] = len(components)
            summary["component_ids"] = [c.get("id") for c in components]
        except Exception:
            summary["note"] = "could not parse assembly JSON"

    elif kind == "part":
        try:
            doc = json.loads(content)
            summary.update({
                "name": doc.get("name"),
                "manufacturer": doc.get("manufacturer"),
                "mpn": doc.get("mpn"),
                "value": doc.get("value"),
            })
        except Exception:
            summary["note"] = "could not parse part JSON"

    elif kind in ("file", "circuit"):
        # Return first 80 chars as a preview plus line count.
        lines = content.split("\n")
        summary["line_count"] = len(lines)
        summary["preview"] = content[:80]

    elif kind == "drawing":
        try:
            doc = json.loads(content)
            summary["sheet_count"] = len(doc.get("sheets", []))
        except Exception:
            summary["note"] = "could not parse drawing JSON"

    return ok_payload(summary)


# ---------------------------------------------------------------------------
# search_kerf_docs
# ---------------------------------------------------------------------------

async def dispatch_search_kerf_docs(ctx: ProjectCtx, args: bytes) -> str:
    from kerf_chat.tools.docs import run_search_kerf_docs
    return await _run(run_search_kerf_docs, ctx, args)


# ---------------------------------------------------------------------------
# import_step — thin wrapper renaming source_url → url
# ---------------------------------------------------------------------------

async def dispatch_import_step(ctx: ProjectCtx, args: bytes) -> str:
    """import_step — renames source_url to url for underlying impl."""
    try:
        a = json.loads(args) if args else {}
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    # Catalog uses 'source_url'; underlying impl uses 'url'.
    if "source_url" in a and "url" not in a:
        a["url"] = a.pop("source_url")

    from kerf_api.tools.file_ops import run_import_step
    return await _run(run_import_step, ctx, json.dumps(a).encode())


# ---------------------------------------------------------------------------
# export_artifact — new tool (stub + best-effort implementation)
# ---------------------------------------------------------------------------

async def dispatch_export_artifact(ctx: ProjectCtx, args: bytes) -> str:
    """export_artifact — routes to export endpoints for supported formats."""
    try:
        a = json.loads(args) if args else {}
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "")
    fmt = a.get("format", "")

    if not file_id or not fmt:
        return err_payload("file_id and format are required", "BAD_ARGS")

    valid_formats = {"gerber", "dxf", "step", "stl", "glb", "png", "pdf"}
    if fmt not in valid_formats:
        return err_payload(f"format must be one of: {', '.join(sorted(valid_formats))}", "BAD_ARGS")

    # Validate file exists in project.
    import uuid as _uuid
    try:
        fid = _uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a UUID", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        "SELECT name, kind FROM files WHERE id = $1 AND project_id = $2 AND deleted_at IS NULL",
        fid, ctx.project_id,
    )
    if not row:
        return err_payload(f"file not found: {file_id}", "NOT_FOUND")

    # Return a download URL if the API exposes one, otherwise a hint.
    # Actual export logic lives in domain-specific routes (tess, render, etc.).
    # For now we return the API download path so the user/agent can navigate there.
    return ok_payload({
        "file_id": file_id,
        "format": fmt,
        "note": (
            f"Export to {fmt} requested for '{row['name']}' (kind={row['kind']}). "
            f"Download URL: /api/files/{file_id}/export?format={fmt}"
        ),
        "download_url": f"/api/files/{file_id}/export?format={fmt}",
    })


# ---------------------------------------------------------------------------
# duplicate_object / delete_object
# ---------------------------------------------------------------------------

async def dispatch_duplicate_object(ctx: ProjectCtx, args: bytes) -> str:
    from kerf_api.tools.object_ops import run_duplicate_object
    return await _run(run_duplicate_object, ctx, args)


async def dispatch_delete_object(ctx: ProjectCtx, args: bytes) -> str:
    from kerf_api.tools.object_ops import run_delete_object
    return await _run(run_delete_object, ctx, args)


# ---------------------------------------------------------------------------
# run_compute — routes by engine enum
# ---------------------------------------------------------------------------

# Job-id prefix used by poll_compute to route to the right status endpoint.
_ENGINE_JOB_PREFIXES: dict[str, str] = {
    "fem": "fem_",
    "cam": "cam_",
    "topo": "topo_",
    "render": "render_",
    "cfd": "cfd_",
    "spice": "spice_",
    "tess": "tess_",
}


async def dispatch_run_compute(ctx: ProjectCtx, args: bytes) -> str:
    """run_compute(engine, file_id, options) — routes to per-engine handler."""
    try:
        a = json.loads(args) if args else {}
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    engine = a.get("engine", "")
    file_id = a.get("file_id", "")
    options = a.get("options", {}) or {}

    if not engine:
        return err_payload("engine is required", "BAD_ARGS")
    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")

    # Build args for the underlying per-engine tool.
    inner: dict = {"file_id": file_id, **options}

    if engine == "fem":
        try:
            from kerf_fem.tools import run_fem_run
        except ImportError:
            return err_payload("FEM engine not available (kerf-fem not installed)", "NOT_AVAILABLE")
        return await _run(run_fem_run, ctx, json.dumps(inner).encode())

    elif engine == "cam":
        try:
            from kerf_cam.tools import run_cam_run
        except ImportError:
            return err_payload("CAM engine not available (kerf-cam not installed)", "NOT_AVAILABLE")
        return await _run(run_cam_run, ctx, json.dumps(inner).encode())

    elif engine == "render":
        try:
            from kerf_render.tools import run_render
        except ImportError:
            return err_payload("Render engine not available (kerf-render not installed)", "NOT_AVAILABLE")
        return await _run(run_render, ctx, json.dumps(inner).encode())

    elif engine == "topo":
        try:
            from kerf_topo.tools import run_topo_run
        except ImportError:
            return err_payload("Topo engine not available (kerf-topo not installed)", "NOT_AVAILABLE")
        return await _run(run_topo_run, ctx, json.dumps(inner).encode())

    elif engine == "cfd":
        try:
            from kerf_cfd.cfd_llm_tools import run_cfd
        except ImportError:
            return err_payload("CFD engine not available (kerf-cfd not installed)", "NOT_AVAILABLE")
        return await _run(run_cfd, ctx, json.dumps(inner).encode())

    elif engine == "spice":
        # SPICE is handled by kerf-electronics or kerf-fem depending on config.
        # Try kerf-electronics first.
        try:
            from kerf_electronics.spice import run_spice  # type: ignore[import]
            return await _run(run_spice, ctx, json.dumps(inner).encode())
        except ImportError:
            pass
        return err_payload("SPICE engine not available", "NOT_AVAILABLE")

    elif engine == "tess":
        try:
            from kerf_tess.tools import run_tess  # type: ignore[import]
            return await _run(run_tess, ctx, json.dumps(inner).encode())
        except ImportError:
            return err_payload("Tess engine not available (kerf-tess not installed)", "NOT_AVAILABLE")

    else:
        return err_payload(
            f"unknown engine '{engine}'; must be fem|cfd|spice|cam|render|topo|tess",
            "BAD_ARGS",
        )


# ---------------------------------------------------------------------------
# poll_compute — routes by job_id prefix
# ---------------------------------------------------------------------------

async def dispatch_poll_compute(ctx: ProjectCtx, args: bytes) -> str:
    """poll_compute(job_id) — routes to the matching engine status handler."""
    try:
        a = json.loads(args) if args else {}
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    job_id = a.get("job_id", "")
    if not job_id:
        return err_payload("job_id is required", "BAD_ARGS")

    inner = json.dumps({"job_id": job_id}).encode()

    if job_id.startswith("fem_") or job_id.startswith("fem-"):
        try:
            from kerf_fem.tools import run_fem_job_status
        except ImportError:
            return err_payload("FEM engine not available", "NOT_AVAILABLE")
        return await _run(run_fem_job_status, ctx, inner)

    elif job_id.startswith("cam_") or job_id.startswith("cam-"):
        try:
            from kerf_cam.tools import run_cam_job_status
        except ImportError:
            return err_payload("CAM engine not available", "NOT_AVAILABLE")
        return await _run(run_cam_job_status, ctx, inner)

    elif job_id.startswith("topo_") or job_id.startswith("topo-"):
        try:
            from kerf_topo.tools import run_topo_status  # type: ignore[import]
        except ImportError:
            # Topo may not expose a separate status function; return a generic response.
            return ok_payload({"job_id": job_id, "status": "unknown", "note": "topo status not available"})
        return await _run(run_topo_status, ctx, inner)

    elif job_id.startswith("render_") or job_id.startswith("render-"):
        try:
            from kerf_render.tools import run_render_job_status  # type: ignore[import]
            return await _run(run_render_job_status, ctx, inner)
        except ImportError:
            return ok_payload({"job_id": job_id, "status": "unknown", "note": "render status not available"})

    else:
        # Unknown prefix — attempt a generic DB lookup by job id.
        return ok_payload({
            "job_id": job_id,
            "status": "unknown",
            "note": "job_id prefix not recognised; check engine-specific job tables",
        })


# ---------------------------------------------------------------------------
# Master dispatch table
# ---------------------------------------------------------------------------

_DISPATCH: dict[str, object] = {
    "read_file": dispatch_read_file,
    "write_file": dispatch_write_file,
    "edit_file": dispatch_edit_file,
    "list_files": dispatch_list_files,
    "search_files": dispatch_search_files,
    "create_file": dispatch_create_file,
    "describe_part": dispatch_describe_part,
    "search_kerf_docs": dispatch_search_kerf_docs,
    "import_step": dispatch_import_step,
    "export_artifact": dispatch_export_artifact,
    "duplicate_object": dispatch_duplicate_object,
    "delete_object": dispatch_delete_object,
    "run_compute": dispatch_run_compute,
    "poll_compute": dispatch_poll_compute,
}


async def dispatch(ctx: ProjectCtx, name: str, args: bytes) -> str:
    """Entry point: route tool name to the matching dispatcher function."""
    fn = _DISPATCH.get(name)
    if fn is None:
        return err_payload(f"unknown tool '{name}'", "UNKNOWN_TOOL")
    return await fn(ctx, args)  # type: ignore[call-arg]
