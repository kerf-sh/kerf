"""
kerf_chat.tools.executor — Public interface used by kerf_api.routes.

  specs(role)          → list[ToolSpec] from the 14-entry TOOL_CATALOG
  execute(ctx, name, args) → str (JSON result or error payload)

The 14 catalog tools replace the previous ~80 per-plugin tool registrations.
The underlying implementations are unchanged; only the LLM-facing names
and registration surface change.
"""
from typing import Optional
from kerf_chat.tools.registry import Tool, ToolSpec, err_payload, ok_payload, Registry
from kerf_chat.tools.catalog import TOOL_CATALOG
from kerf_core.utils.context import ProjectCtx

# Write-capable tools (viewers are blocked from these).
_WRITE_TOOLS = frozenset([
    "write_file",
    "edit_file",
    "create_file",
    "import_step",
    "export_artifact",
    "duplicate_object",
    "delete_object",
    "run_compute",
])


def specs(role: str) -> list[ToolSpec]:
    """Return the active tool catalog filtered by role.

    Viewers get read-only tools only (write tools are hidden entirely so
    the LLM doesn't try to call them and get a FORBIDDEN error back).
    """
    if role == "viewer":
        return [t for t in TOOL_CATALOG if t.name not in _WRITE_TOOLS]
    return list(TOOL_CATALOG)


def find(name: str) -> Optional[Tool]:
    """Legacy look-up in the old Registry (kept for backward compat)."""
    for t in Registry:
        if t.spec.name == name:
            return t
    return None


async def execute(ctx: ProjectCtx, name: str, args: bytes) -> str:
    """Dispatch a tool call through the unified dispatcher.

    Falls back to the legacy Registry for any tool name not in the new
    catalog (e.g. direct server-side calls from integration tests).
    """
    from kerf_chat.tools.dispatcher import dispatch, _DISPATCH

    if name in _DISPATCH:
        # Enforce write gate for viewer role.
        if name in _WRITE_TOOLS and ctx.role == "viewer":
            return err_payload(f"viewers cannot use {name}", "FORBIDDEN")
        if not args:
            args = b"{}"
        return await dispatch(ctx, name, args)

    # Legacy fall-through: tool may still be in the old Registry
    # (e.g. server-side calls, integration tests, direct plugin invocations).
    tool = find(name)
    if tool is None:
        return err_payload(f"unknown tool {name}", "UNKNOWN_TOOL")
    if tool.write and ctx.role == "viewer":
        return err_payload(f"viewers cannot use {name}", "FORBIDDEN")
    if not args:
        args = b"{}"
    try:
        return await tool.run(ctx, args)
    except Exception as e:
        return err_payload(str(e), "ERROR")
