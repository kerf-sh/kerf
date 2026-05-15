"""
kerf-imports plugin registration.

Wires KiCad, FreeCAD, Rhino3dm import routes and Rhino-parity tools
into a Kerf plugin.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


async def register(app: "FastAPI", ctx):
    """Entry point called by the Kerf plugin loader."""

    # ── HTTP routes ──────────────────────────────────────────────────────
    from kerf_imports.freecad import router as freecad_router
    from kerf_imports.kicad import router as kicad_router
    from kerf_imports.kicad_library import router as kicad_library_router
    from kerf_imports.rhino3dm_route import router as rhino3dm_router
    from kerf_imports.dxf.route import router as dxf_router

    app.include_router(freecad_router, tags=["imports"])
    app.include_router(kicad_router, tags=["imports"])
    app.include_router(kicad_library_router, tags=["imports"])
    app.include_router(rhino3dm_router, tags=["imports"])
    app.include_router(dxf_router, tags=["imports"])

    # ── LLM tools ────────────────────────────────────────────────────────
    provides = []
    _register_tools(ctx, provides)

    # Gate capabilities on optional deps
    try:
        import kiutils  # noqa: F401
        provides.append("imports.kicad")
    except ImportError:
        logger.info("kerf-imports: kiutils not available; KiCad import disabled")

    try:
        from OCC.Core import BRepAlgoAPI  # noqa: F401
        provides.append("imports.freecad")
    except ImportError:
        logger.info("kerf-imports: pythonocc not available; FreeCAD import disabled")

    try:
        import rhino3dm  # noqa: F401
        provides.append("imports.rhino3dm")
    except ImportError:
        logger.info("kerf-imports: rhino3dm not available; Rhino3dm import disabled")

    # SubD/mesh are pure-Python analysis — always provided
    provides.append("imports.subd-mesh")

    try:
        from kerf_imports.dwg.bridge import dwg_bridge_available
        if dwg_bridge_available():
            provides.append("imports.dwg")
        else:
            logger.info("kerf-imports: libredwg not available; DWG import disabled")
    except Exception:
        logger.info("kerf-imports: DWG bridge check failed; DWG import disabled")

    try:
        from kerf_core.plugin import PluginManifest  # type: ignore
    except ImportError:
        return {
            "name": "imports",
            "version": "0.1.0",
            "provides": provides,
            "depends": ["cad-core"],
        }

    return PluginManifest(
        name="imports",
        version="0.1.0",
        provides=provides,
        depends=["cad-core"],
    )


def _register_tools(ctx, provides: list) -> None:
    """Register all imports/Rhino-parity LLM tools into ctx.tools."""
    tool_modules = [
        "kerf_imports.tools.import_3dm",
        "kerf_imports.tools.import_freecad",
        "kerf_imports.tools.import_dxf",
        "kerf_imports.tools.subd",
        "kerf_imports.tools.mesh",
        "kerf_imports.tools.curve_ops",
        "kerf_imports.tools.draft",
        "kerf_imports.tools.inspection",
        "kerf_imports.tools.graph",
        "kerf_imports.tools.feature_helix",
        "kerf_imports.tools.feature_multi_transform",
        "kerf_imports.tools.feature_rib",
        "kerf_imports.tools.sheet_revisions",
        "kerf_imports.tools.import_dwg",
    ]

    for module_path in tool_modules:
        try:
            import importlib
            mod = importlib.import_module(module_path)
            if hasattr(mod, "TOOLS"):
                for name, spec, handler in mod.TOOLS:
                    ctx.tools.register(name, spec, handler)
        except Exception as exc:
            logger.warning("kerf-imports: failed to load %s: %s", module_path, exc)
