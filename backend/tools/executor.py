import json
from typing import Optional
from tools.registry import Tool, ToolSpec, err_payload, ok_payload, Registry
from tools.context import ProjectCtx


def specs(role: str) -> list[ToolSpec]:
    out = []
    for t in Registry:
        if t.write and role == "viewer":
            continue
        out.append(t.spec)
    return out


def find(name: str) -> Optional[Tool]:
    for t in Registry:
        if t.spec.name == name:
            return t
    return None


async def execute(ctx: ProjectCtx, name: str, args: bytes) -> str:
    tool = find(name)
    if tool is None:
        return err_payload(f"unknown tool {name}", "UNKNOWN_TOOL")
    if tool.write and ctx.role == "viewer":
        return err_payload(f"viewers cannot use {name}", "FORBIDDEN")
    if not args:
        args = b"{}"
    try:
        out = await tool.run(ctx, args)
        return out
    except Exception as e:
        return err_payload(str(e), "ERROR")
