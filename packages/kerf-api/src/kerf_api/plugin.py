"""kerf-api plugin entry-point.

Registers /api/* routes and LLM tools for file ops, object ops, scaffolding,
revisions, configurations, equations, validation, PCB layers, project layers,
and materials.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI

from kerf_core.plugin import PluginManifest

logger = logging.getLogger(__name__)

PLUGIN_DEPENDS = ["kerf-auth"]


async def register(app: FastAPI, ctx) -> PluginManifest:
    from kerf_api.routes import router
    from kerf_api.routes_atopile import router as atopile_router
    app.include_router(router, prefix="/api", tags=["api"])
    from kerf_api.routes_git_diff import router as git_diff_router
    app.include_router(git_diff_router, prefix="/api", tags=["git-diff"])
    app.include_router(atopile_router, tags=["atopile"])

    _register_tools(ctx)

    ctx.logger.info("kerf-api: registered /api routes and LLM tools")

    return PluginManifest(
        name="kerf-api",
        version="0.1.0",
        provides=["api.rest", "files.crud", "projects.crud"],
        depends=["kerf-auth"],
    )


def _register_tools(ctx) -> None:
    """Register all kerf-api LLM tools into ctx.tools."""

    tool_modules = [
        "kerf_api.tools.file_ops",
        "kerf_api.tools.object_ops",
        "kerf_api.tools.scaffold",
        "kerf_api.tools.revisions",
        "kerf_api.tools.configurations",
        "kerf_api.tools.equations",
        "kerf_api.tools.validation",
        "kerf_api.tools.project_layers",
        "kerf_api.tools.material",
    ]

    import importlib

    for module_path in tool_modules:
        try:
            mod = importlib.import_module(module_path)
            # Each module registers its tools via the @register decorator into
            # the legacy registry when imported.  We also expose them to the
            # plugin tool registry by iterating the module's _compat registry
            # OR by importing the spec/handler pairs directly.
            _register_module_tools(ctx, mod, module_path)
        except Exception as exc:
            logger.warning("kerf-api: failed to load %s: %s", module_path, exc)


def _register_module_tools(ctx, mod, module_path: str) -> None:
    """Register all (spec, handler) pairs from a tool module into ctx.tools."""

    # Build a mapping of handler_fn -> spec from the module's @register calls.
    # Since the tools use the try/except compat shim, on import the @register
    # decorator may have fired into either the legacy tools.registry.Registry
    # list or the kerf_api._compat._registry list.  We walk the module's
    # attributes to find (spec_var, handler_var) pairs by name convention.
    registered = 0
    attrs = dir(mod)
    # Find all *_spec variables that have a `.name` attribute (ToolSpec-like).
    spec_vars = {
        name[:-5]: getattr(mod, name)
        for name in attrs
        if name.endswith("_spec") and hasattr(getattr(mod, name), "name")
    }
    for base_name, spec in spec_vars.items():
        handler_name = f"run_{base_name}"
        handler = getattr(mod, handler_name, None)
        if handler is None:
            logger.warning("kerf-api: %s has spec %s_spec but no run_%s handler",
                           module_path, base_name, base_name)
            continue
        tool_name = spec.name
        try:
            ctx.tools.register(tool_name, spec, handler)
            registered += 1
        except ValueError as exc:
            # Already registered (e.g. duplicate across modules) — skip.
            logger.debug("kerf-api: skipping duplicate tool '%s': %s", tool_name, exc)

    if registered:
        logger.debug("kerf-api: registered %d tool(s) from %s", registered, module_path)
