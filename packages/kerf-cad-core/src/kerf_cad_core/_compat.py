"""Compatibility shims for running kerf_cad_core outside of the legacy backend."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict


_registry: list = []


def register(spec: "ToolSpec", write: bool = False):
    def decorator(fn: Callable) -> Callable:
        _registry.append({"spec": spec, "write": write, "fn": fn})
        return fn
    return decorator


def ok_payload(v: Any) -> str:
    return json.dumps(v)


def err_payload(msg: str, code: str) -> str:
    return json.dumps({"error": msg, "code": code})


class ProjectCtx:
    def __init__(self, pool=None, project_id=None, user_id=None, storage=None,
                 http_client=None, file_revisions_max: int = 200, role: str = "owner"):
        self.pool = pool
        self.project_id = project_id
        self.user_id = user_id
        self.storage = storage
        self.http_client = http_client
        self.file_revisions_max = file_revisions_max
        self.role = role


async def resolve_path(ctx: "ProjectCtx", path: str) -> dict:
    """Stub resolve_path for standalone use; real impl in tools.file_ops."""
    return {"exists": True, "path": path}
