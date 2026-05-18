"""
kerf-woodworking plugin registration.

Wires woodworking joinery, cut-list, and grain-check tools into a Kerf plugin.
"""
from __future__ import annotations

import importlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

_TOOL_MODULES = [
    "kerf_woodworking.tools",
]


async def register(app: "FastAPI", ctx):
    """Entry point called by the Kerf plugin loader."""

    provides: list[str] = []
    _register_tools(ctx, provides)

    provides += [
        "woodworking.joinery",
        "woodworking.cut_list",
        "woodworking.grain",
    ]

    try:
        from kerf_core.plugin import PluginManifest  # type: ignore
    except ImportError:
        return {
            "name": "woodworking",
            "version": "0.1.0",
            "provides": provides,
            "depends": [],
        }

    return PluginManifest(
        name="woodworking",
        version="0.1.0",
        provides=provides,
        depends=[],
    )


def _register_tools(ctx, provides: list) -> None:
    """Register all woodworking LLM tools into ctx.tools."""
    for module_path in _TOOL_MODULES:
        try:
            mod = importlib.import_module(module_path)
            if hasattr(mod, "TOOLS"):
                for name, spec, handler in mod.TOOLS:
                    ctx.tools.register(name, spec, handler)
        except Exception as exc:
            logger.warning(
                "kerf-woodworking: failed to load %s: %s", module_path, exc
            )
