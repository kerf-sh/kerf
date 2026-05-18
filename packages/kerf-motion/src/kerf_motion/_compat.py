"""
Compatibility shims for running kerf_motion outside the main backend.

When kerf_motion is used as a plugin (and kerf_chat.tools.registry /
kerf_core.utils.context are not on the path) these thin replacements
allow unit tests to import cleanly.
"""

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


def register(spec: ToolSpec, write: bool = False):
    def decorator(fn: Callable) -> Callable:
        _registry.append({"spec": spec, "write": write, "fn": fn})
        return fn
    return decorator


def ok_payload(v: Any) -> str:
    return json.dumps(v)


def err_payload(msg: str, code: str) -> str:
    return json.dumps({"error": msg, "code": code})


class ProjectCtx:
    """Minimal stand-in for kerf_core.utils.context.ProjectCtx."""
    def __init__(self, pool=None, project_id=None, user_id=None, storage=None):
        self.pool = pool
        self.project_id = project_id
        self.user_id = user_id
        self.storage = storage
