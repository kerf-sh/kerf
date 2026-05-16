"""
kerf-electronics plugin registration.

Wires RF, SPICE, autoroute and copper-pour routes + LLM tools into a Kerf plugin.
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
    from kerf_electronics.routes_rf import router as rf_router
    from kerf_electronics.routes_spice import router as spice_router
    from kerf_electronics.routes_autoroute import router as autoroute_router
    from kerf_electronics.routes_pour import router as pour_router

    app.include_router(rf_router, tags=["electronics"])
    app.include_router(spice_router, tags=["electronics"])
    app.include_router(autoroute_router, tags=["electronics"])
    app.include_router(pour_router, tags=["electronics"])

    # ── LLM tools ────────────────────────────────────────────────────────
    provides = []
    _register_tools(ctx, provides)

    # Probe which optional deps are available
    try:
        import skrf  # noqa: F401
        provides.append("electronics.rf")
    except ImportError:
        logger.info("kerf-electronics: scikit-rf not available; RF capability disabled")

    # ngspice is a system binary — always declare the route, gate at runtime
    provides.append("electronics.spice")

    # FreeRouting is auto-downloaded — always declare
    provides.append("electronics.autoroute")

    # Copper pour uses shapely (optional)
    provides.append("electronics.pour")

    # Fab output (Gerber, Excellon, P&P, BOM, IPC-2581) — pure Python, always available
    provides.append("electronics.fab")

    # IPC-D-356A netlist export + connectivity report — pure Python, always available
    provides.append("electronics.ipc_netlist")

    # Testpoint auto-placement + bed-of-nails fixture report — pure Python, always available
    provides.append("electronics.testpoint")

    # 3D STEP board export — requires pythonOCC (optional)
    try:
        from kerf_electronics.fab.board_step import _OCC_AVAILABLE as _step_occ
        if _step_occ:
            provides.append("electronics.board_step")
        else:
            logger.info(
                "kerf-electronics: pythonOCC not available; "
                "3D board STEP export disabled (export_board_step tool still registered "
                "and returns a friendly error when called without OCC)"
            )
    except ImportError:
        logger.info("kerf-electronics: board_step module unavailable")

    try:
        from kerf_core.plugin import PluginManifest  # type: ignore
    except ImportError:
        return {
            "name": "electronics",
            "version": "0.1.0",
            "provides": provides,
            "depends": [],
        }

    return PluginManifest(
        name="electronics",
        version="0.1.0",
        provides=provides,
        depends=[],
    )


def _register_tools(ctx, provides: list) -> None:
    """Register all electronics LLM tools into ctx.tools."""
    tool_modules = [
        "kerf_electronics.tools.erc",
        "kerf_electronics.tools.buses",
        "kerf_electronics.tools.net_classes",
        "kerf_electronics.tools.length_tuning",
        "kerf_electronics.tools.via_stitching",
        "kerf_electronics.tools.shove_router",
        "kerf_electronics.tools.pad_overrides",
        "kerf_electronics.tools.hier_schematic",
        "kerf_electronics.tools.rf",
        "kerf_electronics.tools.autoroute",
        "kerf_electronics.tools.pour",
        "kerf_electronics.tools.pcb_drc",
        "kerf_electronics.tools.drc_presets",
        "kerf_electronics.tools.pcb_layer_tools",
        "kerf_electronics.tools.routing",
        "kerf_electronics.tools.sim",
        "kerf_electronics.tools.fab",
        "kerf_electronics.tools.diffpair",
        "kerf_electronics.tools.panelize",
        "kerf_electronics.tools.ipc_netlist",
        "kerf_electronics.tools.spice_lib",
        "kerf_electronics.tools.idf_export",
        "kerf_electronics.tools.lib_mgmt",
        "kerf_electronics.tools.netlist_export",
        "kerf_electronics.tools.testpoint",
        "kerf_electronics.tools.variants",
        "kerf_electronics.tools.odbpp_export",
        "kerf_electronics.tools.si",
        "kerf_electronics.tools.pdn",
        "kerf_electronics.tools.bom_cost",
        "kerf_electronics.tools.flex_stackup",
        "kerf_electronics.tools.eye",
        "kerf_electronics.tools.thermal",
        "kerf_electronics.emc.tools",
        "kerf_electronics.battery.tools",
        "kerf_electronics.rfmatch.tools",
        "kerf_electronics.afilter.tools",
        "kerf_electronics.leddriver.tools",
    ]

    for module_path in tool_modules:
        try:
            import importlib
            mod = importlib.import_module(module_path)
            if hasattr(mod, "TOOLS"):
                for name, spec, handler in mod.TOOLS:
                    ctx.tools.register(name, spec, handler)
        except Exception as exc:
            logger.warning("kerf-electronics: failed to load %s: %s", module_path, exc)
