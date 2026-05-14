"""
LLM tool: run_wireviz

Compiles the YAML source of a .wiring file into an SVG wiring diagram by
calling the pyworker POST /run-wireviz route, then stores the SVG as a
derived artifact alongside the source file.

Schema:
  { "source": "<WireViz YAML string>" }

Returns:
  ok_payload({ "svg": "<SVG string>", "warnings": [...], "svg_path": "/..." })
  err_payload(...) on failure.
"""
from __future__ import annotations

import json
import uuid

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
    from kerf_core.utils.context import ProjectCtx
except ImportError:
    from kerf_wiring._compat import ToolSpec, err_payload, ok_payload, register, ProjectCtx  # type: ignore


run_wireviz_spec = ToolSpec(
    name="run_wireviz",
    description=(
        "Compile a WireViz YAML harness description to an SVG wiring diagram. "
        "Provide the raw YAML source string. "
        "Returns the SVG string and any warnings. "
        "The SVG is also stored as a derived file next to the .wiring source."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": (
                    "WireViz YAML content describing connectors, cables, and "
                    "connections.  See llm_docs/wiring.md for the schema."
                ),
            },
            "wiring_path": {
                "type": "string",
                "description": (
                    "Optional: absolute path to the .wiring file in the project "
                    "tree (e.g. /harness/main.wiring).  When provided the SVG is "
                    "stored as a sibling .svg file."
                ),
            },
        },
        "required": ["source"],
    },
)


@register(run_wireviz_spec, write=True)
async def run_wireviz(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    source = a.get("source", "")
    wiring_path = a.get("wiring_path", "")

    if not source or not source.strip():
        return err_payload("source is required", "BAD_ARGS")

    # ── Call pyworker ─────────────────────────────────────────────────────────
    pyworker_url = "http://localhost:9090"
    try:
        resp = ctx.http_client.post(
            f"{pyworker_url}/run-wireviz",
            json={"source": source},
            timeout=60.0,
        )
    except Exception as exc:
        return err_payload(f"wireviz worker unavailable: {exc}", "WORKER_ERROR")

    if resp.status_code != 200:
        return err_payload(
            f"wireviz worker returned status {resp.status_code}",
            "WORKER_ERROR",
        )

    try:
        result = resp.json()
    except Exception:
        return err_payload("invalid wireviz response", "ERROR")

    svg = result.get("svg")
    warnings = result.get("warnings", [])

    if not svg:
        return err_payload(
            "WireViz returned no SVG. " + "; ".join(warnings),
            "WIREVIZ_ERROR",
        )

    # ── Store SVG as a derived artifact ──────────────────────────────────────
    svg_path = ""
    if wiring_path and ctx.pool:
        svg_path = _svg_path_for(wiring_path)
        try:
            await _upsert_file(ctx, svg_path, svg)
        except Exception as exc:
            warnings.append(f"SVG storage failed: {exc}")

    return ok_payload({
        "svg": svg,
        "warnings": warnings,
        "svg_path": svg_path,
    })


def _svg_path_for(wiring_path: str) -> str:
    """Derive the sibling .svg path from a .wiring path."""
    clean = wiring_path.rstrip("/")
    if clean.lower().endswith(".wiring"):
        return clean[:-7] + ".wiring.svg"
    return clean + ".svg"


async def _upsert_file(ctx: ProjectCtx, path: str, content: str) -> None:
    """Insert or update a file record at `path` with the given content."""
    parts = [p for p in path.strip("/").split("/") if p]
    if not parts:
        return

    leaf = parts[-1]
    parent_id = None

    # Ensure parent folders exist
    for i in range(len(parts) - 1):
        folder_name = parts[i]
        existing = await ctx.pool.fetchrow(
            "SELECT id FROM files WHERE project_id = $1 AND name = $2 "
            "AND parent_id IS NOT DISTINCT FROM $3 AND kind = 'folder' AND deleted_at IS NULL",
            ctx.project_id, folder_name, parent_id,
        )
        if existing:
            parent_id = existing["id"]
        else:
            parent_id = await ctx.pool.fetchval(
                "INSERT INTO files(project_id, parent_id, name, kind, content) "
                "VALUES ($1, $2, $3, 'folder', '{}') RETURNING id",
                ctx.project_id, parent_id, folder_name,
            )

    existing = await ctx.pool.fetchrow(
        "SELECT id FROM files WHERE project_id = $1 AND name = $2 "
        "AND parent_id IS NOT DISTINCT FROM $3 AND deleted_at IS NULL",
        ctx.project_id, leaf, parent_id,
    )
    if existing:
        await ctx.pool.execute(
            "UPDATE files SET content = $1 WHERE id = $2",
            content, existing["id"],
        )
    else:
        await ctx.pool.execute(
            "INSERT INTO files(project_id, parent_id, name, kind, content) "
            "VALUES ($1, $2, $3, 'file', $4)",
            ctx.project_id, parent_id, leaf, content,
        )
