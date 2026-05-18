"""Compatibility shims for running kerf_woodworking tools outside of the legacy backend.

Provides poison-proof local definitions of ``ToolSpec``, ``Tool``, ``Registry``,
``register``, ``ok_payload`` and ``err_payload``. We deliberately do NOT
delegate to ``kerf_chat.tools.registry`` for the *types* here: that module is
sometimes monkey-patched by sibling test files, and any module that imports the
canonical ToolSpec after that replacement would pick up the broken class and
fail at attribute access.  By keeping a self-contained dataclass here the
woodworking modules remain robust to that test-time pollution while still
emitting tool specifications that are structurally identical to the canonical
kerf_chat ones.

``register`` does still co-operate with ``kerf_chat.tools.registry`` when that
module is loaded — registrations are mirrored into the canonical ``Registry``
list so the legacy plugin loader keeps working.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, Callable, List, Optional


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict


@dataclass
class Tool:
    spec: ToolSpec
    write: bool = False
    run: Optional[Callable] = None


# Mirrors kerf_chat.tools.registry.Registry — populated by @register.
Registry: List[Tool] = []


def register(spec: "ToolSpec", write: bool = False):
    def decorator(fn: Callable) -> Callable:
        Registry.append(Tool(spec=spec, write=write, run=fn))
        # Mirror into kerf_chat.tools.registry if present so the canonical
        # registry (or any test-installed stub under that key) still sees the
        # registration. We tolerate any error / poisoned-class shape.
        _kc = sys.modules.get("kerf_chat.tools.registry")
        if _kc is not None:
            try:
                _kc_register = getattr(_kc, "register", None)
                if callable(_kc_register):
                    _kc_register(spec, write=write)(fn)
            except Exception:
                pass
        return fn
    return decorator


def ok_payload(v: Any) -> str:
    return json.dumps(v)


def err_payload(msg: str, code: str) -> str:
    return json.dumps({"error": msg, "code": code})
