"""
kerf-bim plugin registration.

Wires the BIM routes and LLM tools into a Kerf plugin app.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


async def register(app: "FastAPI", ctx):
    """Entry point called by the Kerf plugin loader."""
    from fastapi import FastAPI  # noqa: F811

    # ── HTTP routes ──────────────────────────────────────────────────────
    from kerf_bim.routes import router as bim_router
    app.include_router(bim_router, tags=["bim"])

    # ── LLM tools ────────────────────────────────────────────────────────
    provides = []
    _register_tools(ctx, provides)

    try:
        from kerf_core.plugin import PluginManifest  # type: ignore
    except ImportError:
        # Fallback manifest dict when kerf_core is not yet available
        return {
            "name": "bim",
            "version": "0.1.0",
            "provides": provides,
            "depends": [],
        }

    return PluginManifest(
        name="bim",
        version="0.1.0",
        provides=provides,
        depends=[],
    )


def _register_tools(ctx, provides: list) -> None:
    """Register all BIM LLM tools into ctx.tools."""
    tool_modules = [
        ("kerf_bim.tools.bim", "bim.ifc-compile"),
        ("kerf_bim.tools.bim_categories", "bim.categories"),
        ("kerf_bim.tools.family", "bim.family"),
        ("kerf_bim.tools.schedule", "bim.schedule"),
        ("kerf_bim.tools.view", "bim.view"),
        ("kerf_bim.tools.sheet", "bim.sheet"),
        ("kerf_bim.tools.stairs", "bim.stairs"),
        ("kerf_bim.tools.railings", "bim.railings"),
        ("kerf_bim.tools.mep", "bim.mep"),
        ("kerf_bim.tools.curtain_wall", "bim.curtain-wall"),
        ("kerf_bim.tools.element_types", "bim.element-types"),
        ("kerf_bim.tools.import_ifc", "bim.ifc-import"),
        ("kerf_bim.tools.export_ifc", "bim.ifc-export"),
    ]

    for module_path, capability in tool_modules:
        try:
            import importlib
            mod = importlib.import_module(module_path)
            # Each tool module calls register() at import time against the
            # legacy backend Registry; here we also register capabilities.
            if hasattr(mod, "TOOLS"):
                for name, spec, handler in mod.TOOLS:
                    ctx.tools.register(name, spec, handler)
            provides.append(capability)
        except Exception as exc:
            logger.warning("kerf-bim: failed to load %s: %s", module_path, exc)

    # IFC compile capability is always provided (route is unconditional)
    if "bim.ifc-compile" not in provides:
        provides.append("bim.ifc-compile")

    # Text DSL and Revit-parity are structural — always declare
    provides.append("bim.text-dsl")
    provides.append("bim.revit-parity")
