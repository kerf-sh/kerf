"""Forwarding shim: registry.py has moved to kerf_chat.tools.registry.

This file exists so that ``from tools.registry import ...`` in backend tool
modules (which are still on sys.path) continues to resolve correctly.
"""
from kerf_chat.tools.registry import (  # noqa: F401
    Registry,
    Tool,
    ToolSpec,
    register,
    ok_payload,
    err_payload,
)

__all__ = ["Registry", "Tool", "ToolSpec", "register", "ok_payload", "err_payload"]
