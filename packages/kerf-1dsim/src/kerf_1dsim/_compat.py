"""
Compatibility shims for running kerf_1dsim outside of the kerf-core backend.

When kerf_1dsim is installed as a plugin (and `tools.registry` / `workers.base`
are not on the path) these thin replacements are used so the module still
imports cleanly.  The real implementations are provided by kerf-core at
runtime — these shims are only needed during unit-testing or standalone import.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable


# ---------------------------------------------------------------------------
# ToolSpec / registry shims
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# ProjectCtx shim
# ---------------------------------------------------------------------------

class ProjectCtx:
    """Minimal stand-in for backend.tools.context.ProjectCtx used in tests."""

    def __init__(self, pool=None, project_id=None, user_id=None, storage=None,
                 http_client=None, file_revisions_max: int = 200):
        self.pool = pool
        self.project_id = project_id
        self.user_id = user_id
        self.storage = storage
        self.http_client = http_client
        self.file_revisions_max = file_revisions_max
