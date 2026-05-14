"""Forwarding shim: executor.py has moved to kerf_chat.tools.executor.

This file exists so that ``from tools.executor import ...`` (and the re-export
in backend/tools/__init__.py) continues to resolve correctly.
"""
from kerf_chat.tools.executor import (  # noqa: F401
    specs,
    find,
    execute,
)
from kerf_chat.tools.registry import Registry  # noqa: F401

__all__ = ["specs", "find", "execute", "Registry"]
